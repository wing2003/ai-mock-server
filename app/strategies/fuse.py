from typing import Tuple, Dict, Any
from app.strategies.base import BaseRiskStrategy
from app.risk.context import RequestContext
from app.services.counter import request_counter_service
from app.core.state import runtime_state
from collections import defaultdict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# 全局错误计数器：{api_key: [(timestamp, error_code), ...]}
error_counter: Dict[str, list] = defaultdict(list)


class ErrorRateFuseStrategy(BaseRiskStrategy):
    """错误率熔断策略"""
    strategy_code = "error_rate_fuse"
    strategy_name = "错误率熔断"
    strategy_type = "fuse"
    default_priority = 121
    default_params = {
        "threshold": 0.5,      # 错误率阈值（50%）
        "window": 60,          # 时间窗口（秒）
        "min_requests": 10     # 最小请求数，低于此数不触发熔断
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        """
        检查 API Key 在指定时间窗口内的错误率是否超过阈值
        
        注意：此策略需要配合中间件记录错误事件才能正常工作
        当前实现为简化版本，仅作为框架占位
        """
        if not ctx.api_key:
            return False, {}
        
        threshold = self.params.get("threshold", 0.5)
        window_seconds = self.params.get("window", 60)
        min_requests = self.params.get("min_requests", 10)
        
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=window_seconds)
        
        # 清理过期记录
        if ctx.api_key in error_counter:
            error_counter[ctx.api_key] = [
                (ts, code) for ts, code in error_counter[ctx.api_key]
                if ts > window_start
            ]
        
        # 获取窗口期内的请求记录
        recent_errors = error_counter.get(ctx.api_key, [])
        total_errors = len(recent_errors)
        
        # 如果请求数不足，不触发熔断
        if total_errors < min_requests:
            return False, {}
        
        # 计算错误率（简化实现：假设所有记录都是错误）
        # 实际生产中需要从数据库或内存中统计总请求数和错误数
        error_rate = 1.0  # 简化：假设全是错误
        
        if error_rate > threshold:
            return True, {
                "message": f"API Key {ctx.api_key[:8]}... error rate {error_rate:.2%} exceeds threshold {threshold:.2%}",
                "error_rate": error_rate,
                "threshold": threshold,
                "total_errors": total_errors,
                "window_seconds": window_seconds
            }
        
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        """触发熔断后，将 Key 标记为节点不可用"""
        ctx.response_code = 503
        ctx.response_error = {
            "error": {
                "message": "Service temporarily unavailable due to high error rate. Please try again later.",
                "type": "service_unavailable",
                "code": "error_rate_fuse_triggered",
                "retry_after": 60  # 建议 60 秒后重试
            }
        }
        
        # 将 Key 状态标记为 node_unavailable
        if ctx.api_key and ctx.api_key_obj:
            request_counter_service.track_key_status(ctx.api_key, "node_unavailable")
            runtime_state.update_key(ctx.api_key_obj.id, status="node_unavailable", updated_at=datetime.utcnow())
            logger.warning(f"Key {ctx.api_key[:8]}... marked as node_unavailable due to high error rate")

    @staticmethod
    def record_error(api_key: str, error_code: int):
        """记录错误事件（供中间件调用）"""
        now = datetime.utcnow()
        error_counter[api_key].append((now, error_code))
        
        # 限制历史记录数量，防止内存泄漏
        if len(error_counter[api_key]) > 1000:
            error_counter[api_key] = error_counter[api_key][-500:]
