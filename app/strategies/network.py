from typing import Tuple, Dict, Any, Set
from app.strategies.base import BaseRiskStrategy
from app.risk.context import RequestContext
from app.services.counter import request_counter_service
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
    """IP 白名单校验策略"""
    strategy_code = "ip_whitelist_strategy"
    strategy_name = "IP 白名单校验"
    strategy_type = "network"
    default_priority = 23
    default_params = {
        "whitelist_ips": [],  # 白名单 IP 列表
        "mode": "strict"      # strict: 仅允许白名单; permissive: 仅拒绝黑名单
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        """检查客户端 IP 是否在白名单中"""
        if not ctx.client_ip:
            return False, {}
        
        whitelist_ips = self.params.get("whitelist_ips", [])
        mode = self.params.get("mode", "strict")
        
        # 如果没有配置白名单，不拦截
        if not whitelist_ips:
            return False, {}
        
        # 严格模式：仅允许白名单中的 IP
        if mode == "strict":
            if ctx.client_ip not in whitelist_ips:
                return True, {
                    "message": f"IP {ctx.client_ip} is not in the whitelist",
                    "client_ip": ctx.client_ip,
                    "mode": "strict"
                }
        # 宽松模式：仅拒绝不在白名单中的 IP（与严格模式相同逻辑）
        else:
            if ctx.client_ip not in whitelist_ips:
                return True, {
                    "message": f"IP {ctx.client_ip} is not allowed",
                    "client_ip": ctx.client_ip,
                    "mode": mode
                }
        
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        """IP 不在白名单中，返回 403"""
        ctx.response_code = 403
        ctx.response_error = {
            "error": {
                "message": "Access denied. Your IP address is not authorized to access this service.",
                "type": "ip_restriction",
                "code": "ip_not_whitelisted"
            }
        }


class IPKeyRelationStrategy(BaseRiskStrategy):
    """单 IP 多 Key 关联检测策略"""
    strategy_code = "ip_key_relation_check"
    strategy_name = "单 IP 多 Key 关联检测"
    strategy_type = "network"
    default_priority = 30
    default_params = {
        "max_keys_per_ip": 5,
        "window_seconds": 3600
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        if not ctx.api_key or not ctx.client_ip:
            return False, {}
        
        max_keys = self.params.get("max_keys_per_ip", 5)
        window_seconds = self.params.get("window_seconds", 3600)
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=window_seconds)
        
        # 记录当前 IP-Key 关联
        ip_key_map[ctx.client_ip][ctx.api_key] = now
        
        # 清理过期记录
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
        """将所有关联的 Key 置为「IP关联风险」状态"""
        ctx.response_code = 403
        ctx.response_error = {
            "error": {
                "message": "IP association risk detected. Multiple keys used from same IP.",
                "type": "ip_risk",
                "code": "ip_association_violation"
            }
        }
        
        # 将该 IP 下所有关联的 Key 标记为 ip_risk
        if ctx.client_ip and ctx.client_ip in ip_key_map:
            affected_keys = list(ip_key_map[ctx.client_ip].keys())
            logger.warning(f"Marking {len(affected_keys)} keys as ip_risk due to IP {ctx.client_ip}: {affected_keys}")
            for key in affected_keys:
                request_counter_service.track_key_status(key, "ip_risk")
        
        # 确保当前请求的 Key 也被标记（防止遗漏）
        if ctx.api_key and ctx.api_key not in ip_key_map.get(ctx.client_ip, {}):
            logger.warning(f"Also marking current key {ctx.api_key[:8]}... as ip_risk")
            request_counter_service.track_key_status(ctx.api_key, "ip_risk")


class KeyIPDriftStrategy(BaseRiskStrategy):
    """单 Key 多 IP 漂移检测策略"""
    strategy_code = "key_ip_drift_check"
    strategy_name = "单 Key 多 IP 漂移检测"
    strategy_type = "network"
    default_priority = 35
    default_params = {
        "max_ips_per_key": 3,
        "window_seconds": 1800
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        if not ctx.api_key or not ctx.client_ip:
            return False, {}
        
        max_ips = self.params.get("max_ips_per_key", 3)
        window_seconds = self.params.get("window_seconds", 1800)
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=window_seconds)
        
        # 记录当前 Key-IP 关联
        key_ip_map[ctx.api_key][ctx.client_ip] = now
        
        # 清理过期记录
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
        """永久封禁该 Key"""
        ctx.response_code = 403
        ctx.response_error = {
            "error": {
                "message": "Key IP drift detected. Possible account theft or credential sharing.",
                "type": "ip_risk",
                "code": "key_ip_drift_violation"
            }
        }
        
        # 永久封禁该 Key
        if ctx.api_key_obj:
            ctx.api_key_obj.status = "banned"
            ctx.api_key_obj.updated_at = datetime.utcnow()
            logger.warning(f"Permanently banned key {ctx.api_key[:8]}... due to IP drift")
