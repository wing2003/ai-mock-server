from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import RiskEvent
from app.core.database import AsyncSessionLocal
import logging

logger = logging.getLogger(__name__)

class RiskEventRecorder:
    """风控事件记录器"""

    async def record_event(self, scene_id: int, strategy_id: int, event_type: str, 
                           error_code: int, api_key: str, ip_address: str, 
                           user_agent: str, model: str, prompt_snippet: str, details: dict):
        """异步记录风控事件"""
        try:
            async with AsyncSessionLocal() as db:
                event = RiskEvent(
                    scene_id=scene_id,
                    strategy_id=strategy_id,
                    event_type=event_type,
                    error_code=error_code,
                    api_key=api_key,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    model=model,
                    prompt_snippet=prompt_snippet[:1000] if prompt_snippet else None,
                    details=details
                )
                db.add(event)
                await db.commit()
                logger.debug(f"Risk event recorded: {event_type} for key {api_key}")
        except Exception as e:
            logger.error(f"Failed to record risk event: {e}", exc_info=True)

# 全局单例
risk_recorder = RiskEventRecorder()
