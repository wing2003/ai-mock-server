from typing import Tuple, Dict, Any, Set
from app.strategies.base import BaseRiskStrategy
from app.risk.context import RequestContext
from app.services.counter import request_counter_service
from app.core.state import runtime_state
from datetime import datetime, timedelta
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# 全局内存缓存：用于追踪 IP-Key 关联关系
# {ip: {key1: last_seen_time, key2: last_seen_time, ...}}
ip_key_map: Dict[str, Dict[str, datetime]] = defaultdict(dict)
# {key: {ip1: last_seen_time, ip2: last_seen_time, ...}}
key_ip_map: Dict[str, Dict[str, datetime]] = defaultdict(dict)


class IPWhitelistStrategy(BaseRiskStrategy):
    """IP 黑白名单校验策略"""
    strategy_code = "ip_whitelist_strategy"
    strategy_name = "IP 黑白名单校验"
    strategy_type = "network"
    default_priority = 23
    default_params = {
        "type": "black",    # "white": 白名单模式（仅允许 ips 中的 IP）；"black": 黑名单模式（拒绝 ips 中的 IP）
        "ips": [],          # IP 列表
        "degrade_key": False
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        """根据 type 模式检查客户端 IP 是否在名单中"""
        if not ctx.client_ip:
            return False, {}
        
        ips = self.params.get("ips", [])
        mode = self.params.get("type", "black")
        
        # 如果没有配置 IP 列表，不拦截
        if not ips:
            return False, {}
        
        if mode == "white":
            # 白名单模式：仅允许 ips 中的 IP，不在名单中则拦截
            if ctx.client_ip not in ips:
                return True, {
                    "message": f"IP {ctx.client_ip} is not in the whitelist",
                    "client_ip": ctx.client_ip,
                    "mode": "white"
                }
        else:
            # 黑名单模式：ips 中的 IP 被拦截，不在名单中则放行
            if ctx.client_ip in ips:
                return True, {
                    "message": f"IP {ctx.client_ip} is in the blacklist",
                    "client_ip": ctx.client_ip,
                    "mode": "black"
                }
        
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        """触发后的处置：返回 403，根据 degrade_key 决定是否变更 Key 状态"""
        mode = self.params.get("type", "black")
        error_msg = (
            "Access denied. Your IP address is not authorized to access this service."
            if mode == "white"
            else "Access denied. Your IP address has been blacklisted."
        )
        ctx.response_code = 403
        ctx.response_error = {
            "error": {
                "message": error_msg,
                "type": "ip_restriction",
                "code": "ip_not_whitelisted" if mode == "white" else "ip_blacklisted"
            }
        }
        
        degrade_key = self.params.get("degrade_key", False)
        if not degrade_key:
            # degrade_key: false — 仅返回 403，不修改 Key 状态
            return
        
        # degrade_key: true — 通过双通道持久化将该 Key 置为 ip_risk
        now = datetime.utcnow()
        if ctx.api_key:
            logger.warning(f"Marking key {ctx.api_key[:8]}... as ip_risk due to IP {ctx.client_ip} ({mode}list)")
            # 通道一：写入 counter 缓存，定时 flush 批量落库
            request_counter_service.track_key_status(ctx.api_key, "ip_risk")
            # 通道二：同步更新 RuntimeState 内存，保证后续请求立即感知
            if ctx.api_key_obj is not None:
                runtime_state.update_key(ctx.api_key_obj.id, status="ip_risk", updated_at=now)


class IPKeyRelationStrategy(BaseRiskStrategy):
    """单 IP 多 Key 关联检测策略"""
    strategy_code = "ip_key_relation_check"
    strategy_name = "单 IP 多 Key 关联检测"
    strategy_type = "network"
    default_priority = 30
    default_params = {
        "max_keys_per_ip": 5,
        "degrade_key": False,
        "window_seconds": 300
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        if not ctx.api_key or not ctx.client_ip:
            return False, {}
        
        max_keys = self.params.get("max_keys_per_ip", 5)
        window_seconds = self.params.get("window_seconds", 300)
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=window_seconds)
        
        # 记录当前 IP-Key 关联
        ip_key_map[ctx.client_ip][ctx.api_key] = now
        
        # 清理过期记录（滑动窗口：超过 window_seconds 的关联自动失效）
        expired_keys = [
            key for key, last_seen in ip_key_map[ctx.client_ip].items()
            if last_seen < window_start
        ]
        for key in expired_keys:
            del ip_key_map[ctx.client_ip][key]
        
        # 检查是否超过阈值
        unique_keys_count = len(ip_key_map[ctx.client_ip])
        if unique_keys_count > max_keys:
            return True, {
                "message": f"IP {ctx.client_ip} used {unique_keys_count} different keys (limit: {max_keys})",
                "ip": ctx.client_ip,
                "keys_count": unique_keys_count,
                "max_allowed": max_keys
            }
        
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        """触发后的处置：返回 403，根据 degrade_key 决定是否变更 Key 状态"""
        ctx.response_code = 403
        ctx.response_error = {
            "error": {
                "message": "IP association risk detected. Multiple keys used from same IP.",
                "type": "ip_risk",
                "code": "ip_association_violation"
            }
        }
        
        degrade_key = self.params.get("degrade_key", False)
        if not degrade_key:
            # degrade_key: false — 仅返回 403，不修改 Key 状态
            # 滑动窗口到期后关联记录自动清理，请求自然恢复
            return
        
        # degrade_key: true — 通过双通道持久化将该 IP 下所有关联 Key 置为 ip_risk
        now = datetime.utcnow()
        if ctx.client_ip and ctx.client_ip in ip_key_map:
            affected_keys = list(ip_key_map[ctx.client_ip].keys())
            logger.warning(f"Marking {len(affected_keys)} keys as ip_risk due to IP {ctx.client_ip}: {affected_keys}")
            for key in affected_keys:
                # 通道一：写入 counter 缓存，定时 flush 批量落库
                request_counter_service.track_key_status(key, "ip_risk")
                # 通道二：同步更新 RuntimeState 内存，保证后续请求立即感知
                key_obj = runtime_state.get_key_by_string(key)
                if key_obj is not None:
                    runtime_state.update_key(key_obj.id, status="ip_risk", updated_at=now)
        
        # 确保当前请求的 Key 也被标记（防止遗漏）
        if ctx.api_key and ctx.api_key not in ip_key_map.get(ctx.client_ip, {}):
            logger.warning(f"Also marking current key {ctx.api_key[:8]}... as ip_risk")
            request_counter_service.track_key_status(ctx.api_key, "ip_risk")
            if ctx.api_key_obj is not None:
                runtime_state.update_key(ctx.api_key_obj.id, status="ip_risk", updated_at=now)


class KeyIPDriftStrategy(BaseRiskStrategy):
    """单 Key 多 IP 漂移检测策略"""
    strategy_code = "key_ip_drift_check"
    strategy_name = "单 Key 多 IP 漂移检测"
    strategy_type = "network"
    default_priority = 35
    default_params = {
        "max_ips_per_key": 3,
        "degrade_key": False,
        "window_seconds": 300
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        if not ctx.api_key or not ctx.client_ip:
            return False, {}
        
        max_ips = self.params.get("max_ips_per_key", 3)
        window_seconds = self.params.get("window_seconds", 300)
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=window_seconds)
        
        # 记录当前 Key-IP 关联
        key_ip_map[ctx.api_key][ctx.client_ip] = now
        
        # 清理过期记录（滑动窗口：超过 window_seconds 的关联自动失效）
        expired_ips = [
            ip for ip, last_seen in key_ip_map[ctx.api_key].items()
            if last_seen < window_start
        ]
        for ip in expired_ips:
            del key_ip_map[ctx.api_key][ip]
        
        # 检查是否超过阈值
        unique_ips_count = len(key_ip_map[ctx.api_key])
        if unique_ips_count > max_ips:
            return True, {
                "message": f"API Key {ctx.api_key[:8]}... used from {unique_ips_count} different IPs (limit: {max_ips})",
                "api_key": ctx.api_key,
                "ips_count": unique_ips_count,
                "max_allowed": max_ips
            }
        
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        """触发后的处置：返回 403，根据 degrade_key 决定是否变更 Key 状态"""
        ctx.response_code = 403
        ctx.response_error = {
            "error": {
                "message": "Key IP drift detected. Possible account theft or credential sharing.",
                "type": "ip_risk",
                "code": "key_ip_drift_violation"
            }
        }
        
        degrade_key = self.params.get("degrade_key", False)
        if not degrade_key:
            # degrade_key: false — 仅返回 403，不修改 Key 状态
            # 滑动窗口到期后关联记录自动清理，请求自然恢复
            return
        
        # degrade_key: true — 通过双通道持久化将该 Key 置为 ip_risk
        now = datetime.utcnow()
        if ctx.api_key:
            logger.warning(f"Marking key {ctx.api_key[:8]}... as ip_risk due to IP drift")
            # 通道一：写入 counter 缓存，定时 flush 批量落库
            request_counter_service.track_key_status(ctx.api_key, "ip_risk")
            # 通道二：同步更新 RuntimeState 内存，保证后续请求立即感知
            if ctx.api_key_obj is not None:
                runtime_state.update_key(ctx.api_key_obj.id, status="ip_risk", updated_at=now)
