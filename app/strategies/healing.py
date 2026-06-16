from typing import Tuple, Dict, Any
from app.strategies.base import BaseRiskStrategy
from app.risk.context import RequestContext
from app.services.counter import request_counter_service
from app.core.state import runtime_state
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class AutoHealingStrategy(BaseRiskStrategy):
    """自动恢复规则策略"""
    strategy_code = "auto_healing_rule"
    strategy_name = "自动恢复规则"
    strategy_type = "self_healing"
    default_priority = 141
    default_params = {
        "healable_statuses": ["temp_limited", "ip_risk", "node_unavailable"],  # 可自愈的状态列表
        "check_interval_seconds": 60,  # 检查间隔（秒）
        "max_heal_attempts": 3  # 最大自愈尝试次数
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        """
        检查当前 Key 是否满足自愈条件
        
        注意：此策略主要用于框架占位，实际的自愈逻辑由后台定时任务执行
        这里仅用于在请求时快速检查并恢复符合条件的 Key
        """
        if not ctx.api_key_obj:
            return False, {}
        
        healable_statuses = self.params.get("healable_statuses", ["temp_limited", "ip_risk", "node_unavailable"])
        
        # 检查 Key 当前状态是否在可自愈列表中
        if ctx.api_key_obj.status not in healable_statuses:
            return False, {}
        
        # 检查是否已超过冷却时间
        if not ctx.api_key_obj.updated_at:
            return False, {}
        
        check_interval = self.params.get("check_interval_seconds", 60)
        cooldown_time = ctx.api_key_obj.updated_at + timedelta(seconds=check_interval)
        
        now = datetime.utcnow()
        if now < cooldown_time:
            # 还在冷却期内，不自愈
            return False, {}
        
        # 满足自愈条件
        return True, {
            "message": f"API Key meets auto-healing conditions. Status: {ctx.api_key_obj.status}",
            "current_status": ctx.api_key_obj.status,
            "cooldown_elapsed": (now - ctx.api_key_obj.updated_at).total_seconds(),
            "required_cooldown": check_interval
        }

    async def after_trigger(self, ctx: RequestContext):
        """执行自愈操作，将 Key 恢复为 active 状态"""
        if not ctx.api_key_obj:
            return
        
        old_status = ctx.api_key_obj.status
        
        # 将 Key 恢复为 active 状态
        if ctx.api_key:
            request_counter_service.track_key_status(ctx.api_key, "active")
        runtime_state.update_key(ctx.api_key_obj.id, status="active", updated_at=datetime.utcnow())
        
        logger.info(f"Auto-healed API Key {ctx.api_key[:8]}... from {old_status} to active")
        
        # 注意：这里不设置 response_code 和 response_error
        # 因为自愈成功后，请求应该继续正常处理
        # 中间件会检测到状态已恢复，允许请求通过
