from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any
from app.risk.context import RequestContext

class BaseRiskStrategy(ABC):
    """风控策略抽象基类"""
    strategy_code: str = ""
    strategy_name: str = ""
    strategy_type: str = ""
    default_priority: int = 100
    default_params: Dict[str, Any] = {}

    def __init__(self, custom_params: Dict[str, Any] = None):
        self.params = {**self.default_params, **(custom_params or {})}

    @abstractmethod
    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        """执行策略校验"""
        raise NotImplementedError

    @abstractmethod
    async def after_trigger(self, ctx: RequestContext):
        """风险触发后的后置处理"""
        raise NotImplementedError
