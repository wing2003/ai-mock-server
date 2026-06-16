from typing import Tuple, Dict, Any
from app.strategies.base import BaseRiskStrategy
from app.risk.context import RequestContext
from app.services.counter import request_counter_service
from app.core.state import runtime_state
from collections import defaultdict
from datetime import datetime, timedelta
import time
import logging

logger = logging.getLogger(__name__)

# 全局请求时间记录：{api_key: [timestamp1, timestamp2, ...]}
request_timestamps: Dict[str, list] = defaultdict(list)


class MachineBehaviorStrategy(BaseRiskStrategy):
    """机器匀速请求检测策略"""
    strategy_code = "machine_behavior_check"
    strategy_name = "机器匀速请求检测"
    strategy_type = "behavior"
    default_priority = 110
    default_params = {
        "interval_deviation_threshold": 0.1,  # 允许的间隔偏差比例 (10%)
        "min_requests_to_check": 5  # 最少需要检查的请求数
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        """
        检测请求间隔是否过于均匀（机器行为特征）
        
        原理：人类用户的请求间隔通常有较大波动，而自动化脚本往往保持固定间隔
        """
        if not ctx.api_key:
            return False, {}
        
        min_requests = self.params.get("min_requests_to_check", 5)
        deviation_threshold = self.params.get("interval_deviation_threshold", 0.1)
        
        now = datetime.utcnow()
        timestamps = request_timestamps[ctx.api_key]
        
        # 添加当前请求时间戳
        timestamps.append(now.timestamp())
        
        # 保留最近 20 个请求的时间戳
        if len(timestamps) > 20:
            timestamps.pop(0)
        
        # 如果请求数不足，不进行检测
        if len(timestamps) < min_requests:
            return False, {}
        
        # 计算相邻请求的时间间隔
        intervals = []
        for i in range(1, len(timestamps)):
            interval = timestamps[i] - timestamps[i-1]
            intervals.append(interval)
        
        # 计算平均间隔和标准差
        avg_interval = sum(intervals) / len(intervals)
        
        if avg_interval == 0:
            return False, {}
        
        # 计算变异系数（标准差 / 平均值）
        variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
        std_dev = variance ** 0.5
        coefficient_of_variation = std_dev / avg_interval
        
        # 如果变异系数小于阈值，说明间隔过于均匀（疑似机器行为）
        if coefficient_of_variation < deviation_threshold:
            return True, {
                "message": f"Machine-like behavior detected. Interval CV: {coefficient_of_variation:.3f} (threshold: {deviation_threshold})",
                "avg_interval": avg_interval,
                "std_dev": std_dev,
                "coefficient_of_variation": coefficient_of_variation,
                "request_count": len(timestamps)
            }
        
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        """检测到机器行为，返回 429 并标记 Key 状态"""
        ctx.response_code = 429
        ctx.response_error = {
            "error": {
                "message": "Unusual request pattern detected. Please slow down your requests.",
                "type": "rate_limit_error",
                "code": "machine_behavior_detected",
                "retry_after": 60
            }
        }
        
        # 将 Key 标记为请求行为异常
        if ctx.api_key and ctx.api_key_obj:
            request_counter_service.track_key_status(ctx.api_key, "behavior_anomaly")
            runtime_state.update_key(ctx.api_key_obj.id, status="behavior_anomaly", updated_at=datetime.utcnow())
            logger.warning(f"Key {ctx.api_key[:8]}... marked as behavior_anomaly due to machine-like pattern")

    @staticmethod
    def cleanup_old_records(max_age_seconds: int = 3600):
        """清理过旧的请求记录，防止内存泄漏"""
        now = datetime.utcnow().timestamp()
        cutoff = now - max_age_seconds
        
        for api_key in list(request_timestamps.keys()):
            request_timestamps[api_key] = [
                ts for ts in request_timestamps[api_key] if ts > cutoff
            ]
            if not request_timestamps[api_key]:
                del request_timestamps[api_key]


class BehaviorAnomalyStrategy(BaseRiskStrategy):
    """综合行为异常检测策略"""
    strategy_code = "behavior_anomaly_check"
    strategy_name = "综合行为异常检测"
    strategy_type = "behavior"
    default_priority = 115
    default_params = {
        "max_requests_per_minute": 120,  # 每分钟最大请求数
        "max_concurrent_sessions": 3,    # 最大并发会话数
        "suspicious_patterns": []        # 可疑模式列表
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        """
        检测多种行为异常模式
        
        包括：
        1. 请求频率异常高
        2. 并发会话数过多
        3. 其他可疑行为模式
        """
        if not ctx.api_key:
            return False, {}
        
        max_rpm = self.params.get("max_requests_per_minute", 120)
        max_sessions = self.params.get("max_concurrent_sessions", 3)
        
        # 检查请求频率（简化实现）
        timestamps = request_timestamps.get(ctx.api_key, [])
        now = datetime.utcnow().timestamp()
        one_minute_ago = now - 60
        
        recent_requests = [ts for ts in timestamps if ts > one_minute_ago]
        
        if len(recent_requests) > max_rpm:
            return True, {
                "message": f"Abnormal request frequency: {len(recent_requests)} RPM (limit: {max_rpm})",
                "reason": "high_frequency",
                "current_rpm": len(recent_requests),
                "max_allowed": max_rpm
            }
        
        # TODO: 可以在此添加更多行为检测逻辑
        # - 并发会话检测
        # - IP 切换频率检测
        # - 请求内容相似度检测
        
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        """检测到行为异常，返回 429 或 403"""
        reason = ctx.trigger_details.get("reason", "unknown")
        
        if reason == "high_frequency":
            ctx.response_code = 429
            ctx.response_error = {
                "error": {
                    "message": "Too many requests. Your request frequency is abnormally high.",
                    "type": "rate_limit_error",
                    "code": "abnormal_request_frequency",
                    "retry_after": 300
                }
            }
        else:
            ctx.response_code = 403
            ctx.response_error = {
                "error": {
                    "message": "Suspicious activity detected. Access temporarily restricted.",
                    "type": "security_error",
                    "code": "behavior_anomaly_detected"
                }
            }
        
        # 将 Key 标记为请求行为异常
        if ctx.api_key and ctx.api_key_obj:
            request_counter_service.track_key_status(ctx.api_key, "behavior_anomaly")
            runtime_state.update_key(ctx.api_key_obj.id, status="behavior_anomaly", updated_at=datetime.utcnow())
            logger.warning(f"Key {ctx.api_key[:8]}... marked as behavior_anomaly: {reason}")
