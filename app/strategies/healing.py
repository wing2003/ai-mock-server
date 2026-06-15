from typing import Tuple, Dict, Any
from app.strategies.base import BaseRiskStrategy
from app.risk.context import RequestContext
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
        ctx.api_key_obj.status = "active"
        ctx.api_key_obj.updated_at = datetime.utcnow()
        
        logger.info(f"Auto-healed API Key {ctx.api_key[:8]}... from {old_status} to active")
        
        # 注意：这里不设置 response_code 和 response_error
        # 因为自愈成功后，请求应该继续正常处理
        # 中间件会检测到状态已恢复，允许请求通过


# 后台自愈服务（保留原有功能，但改为调用策略逻辑）
class HealingService:
    """自愈服务：负责定期检查并恢复受限的 API Key"""
    
    def __init__(self):
        self.is_running = False
        self.task = None

    async def start(self):
        """启动后台自愈任务"""
        if self.is_running:
            return
        self.is_running = True
        import asyncio
        self.task = asyncio.create_task(self._healing_loop())
        logger.info("Healing service started.")

    async def stop(self):
        """停止后台自愈任务"""
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Healing service stopped.")

    async def _healing_loop(self):
        """自愈循环：每 60 秒检查一次"""
        import asyncio
        while self.is_running:
            try:
                await self._check_and_heal()
            except Exception as e:
                logger.error(f"Healing loop error: {e}")
            # 等待 60 秒后再次执行
            await asyncio.sleep(60)

    async def _check_and_heal(self):
        """执行具体的自愈逻辑"""
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.base import ApiKey
        from app.services.config import config_service
        
        async with AsyncSessionLocal() as db:
            now = datetime.utcnow()
            
            # 1. 处理临时限流 (temp_limited) 和 IP关联风险 (ip_risk)
            interval_str = await config_service.get_value("temp_limited_interval", "300")
            interval = int(interval_str)
            cooldown_time = now - timedelta(seconds=interval)
            
            result = await db.execute(
                select(ApiKey).where(
                    ApiKey.status.in_(["temp_limited", "ip_risk"]),
                    ApiKey.updated_at <= cooldown_time
                )
            )
            keys_to_heal = result.scalars().all()

            for key in keys_to_heal:
                logger.info(f"Auto-healing API Key from {key.status}: {key.api_key[:8]}...")
                key.status = "active"
            
            # 2. 处理节点不可用 (node_unavailable) - 试探性恢复
            node_result = await db.execute(
                select(ApiKey).where(
                    ApiKey.status == "node_unavailable",
                    ApiKey.updated_at <= cooldown_time
                )
            )
            node_keys = node_result.scalars().all()
            for key in node_keys:
                key.status = "active"  # 尝试恢复

            if keys_to_heal or node_keys:
                await db.commit()
                logger.info(f"Successfully healed {len(keys_to_heal) + len(node_keys)} API Keys.")


# 全局单例
healing_service = HealingService()
