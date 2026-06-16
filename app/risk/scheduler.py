from app.risk.context import RequestContext
from app.risk.recorder import risk_recorder
from app.core.state import runtime_state
import logging

logger = logging.getLogger(__name__)


class RiskChainScheduler:
    """
    风控链调度器（全局单例）
    
    策略列表和策略 ID 映射均从 RuntimeState 内存读取，
    不再自行维护 enabled_strategies 和 strategy_id_map。
    """

    async def execute_chain(self, ctx: RequestContext) -> bool:
        """
        执行风控全链路，返回是否触发风险。
        策略列表来自 runtime_state.enabled_strategies（按优先级升序排列）。
        """
        strategies = runtime_state.enabled_strategies
        strategy_id_map = runtime_state.strategy_id_map

        logger.debug(
            f"Executing risk chain for request {ctx.request_id}, "
            f"strategies count: {len(strategies)}"
        )

        for strategy in strategies:
            try:
                logger.debug(f"Running strategy: {strategy.strategy_code}")
                triggered, details = await strategy.execute(ctx)
                if triggered:
                    logger.warning(f"Risk triggered by {strategy.strategy_code}: {details}")
                    ctx.risk_triggered = True
                    ctx.trigger_strategy_code = strategy.strategy_code
                    ctx.trigger_details = details
                    await strategy.after_trigger(ctx)

                    # 记录风控事件（strategy_id 从 RuntimeState 映射获取）
                    await risk_recorder.record_event(
                        scene_id=ctx.scene_id,
                        strategy_id=strategy_id_map.get(strategy.strategy_code),
                        event_type=strategy.strategy_type,
                        error_code=ctx.response_code,
                        api_key=ctx.api_key,
                        ip_address=ctx.client_ip,
                        user_agent=ctx.user_agent,
                        model=ctx.model,
                        prompt_snippet=ctx.prompt_content,
                        details=details,
                    )
                    return True
            except Exception as e:
                logger.error(
                    f"Strategy execution error {strategy.strategy_code}: {e}", exc_info=True
                )
        return False


# 全局单例
risk_scheduler = RiskChainScheduler()
