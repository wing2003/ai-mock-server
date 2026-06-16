import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)


class RuntimeState:
    """
    全局运行时状态管理器（全局单例）
    
    场景启动时从数据库一次性加载 Scene、Keys、Strategies 到内存，
    所有运行时读取操作（API Key 校验、风控链执行、定时刷库、自愈）均从内存获取，
    界面修改 Key 属性或策略配置时实时同步到本对象，场景停止时清空所有内存数据。
    """

    def __init__(self):
        # 当前运行中的场景 ORM 对象
        self.scene: Optional[Any] = None
        # 已启用的策略实例列表，按 default_priority 升序排列
        self.enabled_strategies: List[Any] = []
        # 策略 code -> strategy_id（数据库 ID）映射，用于事件记录
        self.strategy_id_map: Dict[str, int] = {}
        # api_key.id -> ApiKey ORM 对象，运行时 Key 全量缓存
        self.keys: Dict[int, Any] = {}
        # api_key 字符串 -> api_key.id，二级索引，用于 Bearer token O(1) 查找
        self.key_lookup: Dict[str, int] = {}
        # 服务是否运行中
        self.is_running: bool = False

    # ------------------------------------------------------------------
    # 场景生命周期
    # ------------------------------------------------------------------

    async def start_scene(self, scene_id: int, db: AsyncSession) -> None:
        """
        启动场景：从数据库加载 Scene、绑定的 Keys、启用的 Strategies 到内存。
        必须在场景启动时调用一次，之后所有读取走内存。
        """
        # 延迟导入避免循环引用
        from app.models.base import (
            Scene, ApiKey, ScenePoolRelation,
            SceneStrategyRelation, StrategyMetadata,
        )

        # 1. 加载场景对象
        result = await db.execute(select(Scene).where(Scene.id == scene_id))
        scene = result.scalar_one_or_none()
        if not scene:
            raise ValueError(f"Scene {scene_id} not found")
        self.scene = scene

        # 2. 加载场景绑定的所有 Key 池的 Keys
        pool_ids_result = await db.execute(
            select(ScenePoolRelation.pool_id).where(ScenePoolRelation.scene_id == scene_id)
        )
        pool_ids = [r[0] for r in pool_ids_result.all()]

        if pool_ids:
            keys_result = await db.execute(
                select(ApiKey).where(
                    ApiKey.pool_id.in_(pool_ids),
                    ApiKey.is_deleted == False,  # noqa: E712
                )
            )
            for key_obj in keys_result.scalars().all():
                self.keys[key_obj.id] = key_obj
                self.key_lookup[key_obj.api_key] = key_obj.id

        # 3. 加载并实例化已启用的策略
        rel_result = await db.execute(
            select(SceneStrategyRelation).where(
                SceneStrategyRelation.scene_id == scene_id,
                SceneStrategyRelation.is_enabled == True,  # noqa: E712
            )
        )
        relations = rel_result.scalars().all()

        for rel in relations:
            meta_result = await db.execute(
                select(StrategyMetadata).where(StrategyMetadata.id == rel.strategy_id)
            )
            meta = meta_result.scalar_one_or_none()
            if not meta or not meta.handler_class:
                continue
            instance = self._instantiate_strategy(meta, rel.custom_params, rel.strategy_id)
            if instance:
                self.enabled_strategies.append(instance)
                self.strategy_id_map[instance.strategy_code] = rel.strategy_id

        # 4. 按优先级升序排列
        self._sort_strategies()

        self.is_running = True
        logger.info(
            f"RuntimeState started for scene '{scene.name}' (id={scene_id}): "
            f"{len(self.keys)} keys, {len(self.enabled_strategies)} strategies loaded."
        )

    def stop_scene(self) -> None:
        """停止场景：清空所有内存数据"""
        scene_name = self.scene.name if self.scene else "unknown"
        self.scene = None
        self.enabled_strategies.clear()
        self.strategy_id_map.clear()
        self.keys.clear()
        self.key_lookup.clear()
        self.is_running = False
        logger.info(f"RuntimeState stopped for scene '{scene_name}'. All in-memory data cleared.")

    # ------------------------------------------------------------------
    # API Key 内存操作
    # ------------------------------------------------------------------

    def get_key_by_string(self, api_key_str: str) -> Optional[Any]:
        """
        通过 Bearer token 字符串 O(1) 查找 ApiKey ORM 对象。
        返回 None 表示 Key 不存在或不属于当前场景绑定的池。
        """
        if not api_key_str:
            return None
        key_id = self.key_lookup.get(api_key_str)
        if key_id is None:
            return None
        return self.keys.get(key_id)

    def update_key(self, key_id: int, **kwargs) -> None:
        """
        更新内存中指定 Key 的属性（status / balance / expire_at / is_deleted 等）。
        若 RuntimeState 未运行或 key_id 不在缓存中则静默忽略。
        """
        if not self.is_running:
            return
        key_obj = self.keys.get(key_id)
        if key_obj is None:
            return
        for attr, value in kwargs.items():
            if hasattr(key_obj, attr):
                setattr(key_obj, attr, value)
        logger.debug(f"RuntimeState: key id={key_id} updated: {list(kwargs.keys())}")

    # ------------------------------------------------------------------
    # 策略内存操作
    # ------------------------------------------------------------------

    def add_strategy(self, instance: Any) -> None:
        """添加策略实例到已启用列表并重新排序"""
        self.enabled_strategies.append(instance)
        self._sort_strategies()
        logger.info(f"RuntimeState: strategy '{instance.strategy_code}' added.")

    def remove_strategy(self, strategy_code: str) -> None:
        """按 strategy_code 移除策略实例"""
        self.enabled_strategies = [
            s for s in self.enabled_strategies if s.strategy_code != strategy_code
        ]
        self.strategy_id_map.pop(strategy_code, None)
        logger.info(f"RuntimeState: strategy '{strategy_code}' removed.")

    def load_strategy_instance(
        self, meta: Any, custom_params: Optional[dict], strategy_id: int
    ) -> Optional[Any]:
        """
        根据 StrategyMetadata 元数据动态实例化策略类。
        成功返回实例，失败返回 None 并记录错误日志。
        """
        import importlib
        try:
            module_path, class_name = meta.handler_class.rsplit('.', 1)
            module = importlib.import_module(module_path)
            strategy_class = getattr(module, class_name)
            instance = strategy_class(custom_params=custom_params or {})
            instance._strategy_id = strategy_id
            return instance
        except Exception as e:
            logger.error(f"Failed to instantiate strategy {meta.handler_class}: {e}")
            return None

    def update_strategy_params(self, strategy_code: str, custom_params: dict) -> None:
        """
        更新策略参数：用新参数重新实例化策略，替换列表中对应位置的实例。
        若 strategy_code 不在当前启用列表中则静默忽略（仅更新 DB，下次启用时生效）。
        """
        for i, strategy in enumerate(self.enabled_strategies):
            if strategy.strategy_code == strategy_code:
                # 获取原策略的类，用新参数重新实例化
                strategy_class = type(strategy)
                new_instance = strategy_class(custom_params=custom_params)
                new_instance._strategy_id = getattr(strategy, '_strategy_id', None)
                self.enabled_strategies[i] = new_instance
                logger.info(f"RuntimeState: strategy '{strategy_code}' params refreshed.")
                return
        logger.debug(
            f"RuntimeState: strategy '{strategy_code}' not in enabled list, params update skipped."
        )

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _instantiate_strategy(
        self, meta: Any, custom_params: Optional[dict], strategy_id: int
    ) -> Optional[Any]:
        """内部方法：根据元数据实例化策略，与 load_strategy_instance 功能相同"""
        return self.load_strategy_instance(meta, custom_params, strategy_id)

    def _sort_strategies(self) -> None:
        """按 default_priority 升序排列策略列表（数字越小优先级越高）"""
        self.enabled_strategies.sort(key=lambda s: s.default_priority)


# 全局单例
runtime_state = RuntimeState()
