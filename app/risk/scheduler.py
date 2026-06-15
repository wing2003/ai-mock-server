from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.base import StrategyMetadata, SceneStrategyRelation
from app.risk.context import RequestContext
from app.risk.recorder import risk_recorder
import logging
import importlib

logger = logging.getLogger(__name__)

class RiskChainScheduler:
    """风控链调度器"""
    
    def __init__(self):
        self.enabled_strategies: List[Any] = []
        self.strategy_id_map: Dict[str, int] = {}

    async def init_for_scene(self, scene_id: int, db: AsyncSession):
        """为指定场景初始化风控链"""
        self.enabled_strategies = []
        
        # 1. 查询场景关联的已启用策略
        result = await db.execute(
            select(SceneStrategyRelation).where(
                SceneStrategyRelation.scene_id == scene_id,
                SceneStrategyRelation.is_enabled == True
            )
        )
        relations = result.scalars().all()
        
        for rel in relations:
            # 2. 获取策略元数据
            meta_result = await db.execute(select(StrategyMetadata).where(StrategyMetadata.id == rel.strategy_id))
            meta = meta_result.scalar_one_or_none()
            
            if meta and meta.handler_class:
                try:
                    # 3. 动态加载策略类
                    module_path, class_name = meta.handler_class.rsplit('.', 1)
                    module = importlib.import_module(module_path)
                    strategy_class = getattr(module, class_name)
                    
                    # 4. 实例化策略（合并自定义参数）
                    custom_params = rel.custom_params or {}
                    strategy_instance = strategy_class(custom_params=custom_params)
                    strategy_instance._strategy_id = rel.strategy_id  # 绑定 ID
                    self.enabled_strategies.append(strategy_instance)
                    self.strategy_id_map[strategy_instance.strategy_code] = rel.strategy_id
                    logger.info(f"Loaded strategy: {meta.strategy_name}")
                except Exception as e:
                    logger.error(f"Failed to load strategy {meta.handler_class}: {e}")
        
        # 5. 按优先级排序
        self.enabled_strategies.sort(key=lambda x: x.default_priority)
        logger.info(f"Risk chain initialized with {len(self.enabled_strategies)} strategies.")

    async def execute_chain(self, ctx: RequestContext) -> bool:
        """执行风控全链路，返回是否触发风险"""
        logger.debug(f"Executing risk chain for request {ctx.request_id}, strategies count: {len(self.enabled_strategies)}")
        for strategy in self.enabled_strategies:
            try:
                logger.debug(f"Running strategy: {strategy.strategy_code}")
                triggered, details = await strategy.execute(ctx)
                if triggered:
                    logger.warning(f"Risk triggered by {strategy.strategy_code}: {details}")
                    ctx.risk_triggered = True
                    ctx.trigger_strategy_code = strategy.strategy_code
                    ctx.trigger_details = details
                    await strategy.after_trigger(ctx)
                    
                    # 记录风控事件
                    await risk_recorder.record_event(
                        scene_id=ctx.scene_id,
                        strategy_id=self.strategy_id_map.get(strategy.strategy_code),
                        event_type=strategy.strategy_type,
                        error_code=ctx.response_code,
                        api_key=ctx.api_key,
                        ip_address=ctx.client_ip,
                        user_agent=ctx.user_agent,
                        model=ctx.model,
                        prompt_snippet=ctx.prompt_content,
                        details=details
                    )
                    return True
            except Exception as e:
                logger.error(f"Strategy execution error {strategy.strategy_code}: {e}", exc_info=True)
        return False

    def cleanup(self):
        """清理资源"""
        self.enabled_strategies = []

# 全局单例
risk_scheduler = RiskChainScheduler()
