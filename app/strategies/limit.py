from typing import Tuple, Dict, Any
from app.risk.context import RequestContext
from app.strategies.base import BaseRiskStrategy
from app.risk.limiter import limiter
from app.services.config import config_service
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class IPRpmLimitStrategy(BaseRiskStrategy):
    """IP 每分钟请求数限制策略"""
    strategy_code: str = "ip_rpm_limit"
    strategy_name: str = "IP 每分钟请求数限制"
    strategy_type: str = "network"
    default_priority: int = 21
    default_params: Dict[str, Any] = {"rpm": 60}

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        rpm_limit = self.params.get("rpm", 60)
        key = f"ip:{ctx.client_ip}"
        if await limiter.is_rate_limited(key, rpm_limit):
            return True, {"message": f"IP {ctx.client_ip} exceeded RPM limit of {rpm_limit}"}
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        if ctx.api_key_obj:
            ctx.api_key_obj.status = "temp_limited"
            ctx.api_key_obj.updated_at = datetime.utcnow()

class IPRphLimitStrategy(BaseRiskStrategy):
    """IP 每小时请求数限制策略"""
    strategy_code: str = "ip_rph_limit"
    strategy_name: str = "IP 每小时请求数限制"
    strategy_type: str = "network"
    default_priority: int = 22
    default_params: Dict[str, Any] = {"rph": 1000}

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        rph_limit = self.params.get("rph", 1000)
        key = f"ip:{ctx.client_ip}"
        if await limiter.is_rate_limited(key, rph_limit, period=3600):
            return True, {"message": f"IP {ctx.client_ip} exceeded RPH limit of {rph_limit}"}
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        if ctx.api_key_obj:
            ctx.api_key_obj.status = "temp_limited"
            ctx.api_key_obj.updated_at = datetime.utcnow()

class GlobalRpmLimitStrategy(BaseRiskStrategy):
    """全局每分钟请求数限制策略"""
    strategy_code: str = "global_rpm_limit"
    strategy_name: str = "全局每分钟请求数限制"
    strategy_type: str = "limit"
    default_priority: int = 61
    default_params: Dict[str, Any] = {"rpm": 2000}

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        rpm_limit = self.params.get("rpm", 2000)
        key = "global"
        if await limiter.is_rate_limited(key, rpm_limit):
            return True, {"message": f"Global RPM limit exceeded: {rpm_limit}"}
        return False, {}

class ApiKeyRpmLimitStrategy(BaseRiskStrategy):
    """API Key 每分钟请求数限制策略"""
    strategy_code: str = "api_key_rpm_limit"
    strategy_name: str = "API Key 每分钟请求数限制"
    strategy_type: str = "limit"
    default_priority: int = 62
    default_params: Dict[str, Any] = {"rpm": 100}

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        if not ctx.api_key:
            return False, {}
        rpm_limit = self.params.get("rpm", 100)
        key = f"key:{ctx.api_key}"
        if await limiter.is_rate_limited(key, rpm_limit):
            return True, {"message": f"API Key {ctx.api_key[:8]}... exceeded RPM limit of {rpm_limit}"}
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        if ctx.api_key_obj:
            ctx.api_key_obj.status = "temp_limited"
            ctx.api_key_obj.updated_at = datetime.utcnow()


class IPConcurrencyLimitStrategy(BaseRiskStrategy):
    """单 IP 并发数限制策略"""
    strategy_code: str = "ip_concurrency_limit"
    strategy_name: str = "单 IP 并发数限制"
    strategy_type: str = "limit"
    default_priority: int = 70
    default_params: Dict[str, Any] = {"max_concurrent": 10}

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        max_concurrent = self.params.get("max_concurrent", 10)
        key = f"ip_concurrent:{ctx.client_ip}"
        if await limiter.is_rate_limited(key, max_concurrent, period=1):
            return True, {"message": f"IP {ctx.client_ip} exceeded concurrent limit of {max_concurrent}"}
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        if ctx.api_key_obj:
            ctx.api_key_obj.status = "temp_limited"
            ctx.api_key_obj.updated_at = datetime.utcnow()


class KeyConcurrencyLimitStrategy(BaseRiskStrategy):
    """单 Key 并发数限制策略"""
    strategy_code: str = "key_concurrency_limit"
    strategy_name: str = "单 Key 并发数限制"
    strategy_type: str = "limit"
    default_priority: int = 71
    default_params: Dict[str, Any] = {"max_concurrent": 5}

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        if not ctx.api_key:
            return False, {}
        max_concurrent = self.params.get("max_concurrent", 5)
        key = f"key_concurrent:{ctx.api_key}"
        if await limiter.is_rate_limited(key, max_concurrent, period=1):
            return True, {"message": f"API Key {ctx.api_key[:8]}... exceeded concurrent limit of {max_concurrent}"}
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        if ctx.api_key_obj:
            ctx.api_key_obj.status = "temp_limited"
            ctx.api_key_obj.updated_at = datetime.utcnow()


class ModelRpmLimitStrategy(BaseRiskStrategy):
    """模型维度每分钟请求数限制策略"""
    strategy_code: str = "model_rpm_limit"
    strategy_name: str = "模型维度 RPM 限制"
    strategy_type: str = "limit"
    default_priority: int = 63
    default_params: Dict[str, Any] = {
        "rpm": 100,
        "model_specific_limits": {}  # {"gpt-4": 50, "gpt-3.5": 200}
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        if not ctx.model:
            return False, {}
        
        # 检查是否有模型特定的限流配置
        model_specific_limits = self.params.get("model_specific_limits", {})
        if ctx.model in model_specific_limits:
            rpm_limit = model_specific_limits[ctx.model]
        else:
            rpm_limit = self.params.get("rpm", 100)
        
        key = f"model:{ctx.model}"
        if await limiter.is_rate_limited(key, rpm_limit):
            return True, {
                "message": f"Model {ctx.model} exceeded RPM limit of {rpm_limit}",
                "model": ctx.model,
                "rpm_limit": rpm_limit
            }
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        # 模型维度限流不改变 Key 状态，仅返回 429
        pass
