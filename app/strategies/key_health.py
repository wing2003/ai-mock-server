from typing import Tuple, Dict, Any
from app.strategies.base import BaseRiskStrategy
from app.risk.context import RequestContext
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ApiKeyBanStrategy(BaseRiskStrategy):
    """API Key 永久封禁校验策略"""
    strategy_code = "api_key_ban_strategy"
    strategy_name = "API Key 永久封禁校验"
    strategy_type = "key_health"
    default_priority = 10
    default_params = {}

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        """检查 API Key 是否被永久封禁"""
        if not ctx.api_key_obj:
            return False, {}
        
        if ctx.api_key_obj.status == "banned":
            return True, {
                "message": f"API Key {ctx.api_key[:8]}... is permanently banned",
                "status": "banned"
            }
        
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        """永久封禁的 Key 直接返回 403"""
        ctx.response_code = 403
        ctx.response_error = {
            "error": {
                "message": "This API key has been permanently banned.",
                "type": "auth_error",
                "code": "api_key_banned"
            }
        }


class ApiKeyExpiredStrategy(BaseRiskStrategy):
    """API Key 过期校验策略"""
    strategy_code = "api_key_expired_strategy"
    strategy_name = "API Key 过期校验"
    strategy_type = "key_health"
    default_priority = 11
    default_params = {}

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        """检查 API Key 是否已过期"""
        if not ctx.api_key_obj:
            return False, {}
        
        # 检查是否有过期时间且已过期
        if ctx.api_key_obj.expire_at and ctx.api_key_obj.expire_at < datetime.utcnow():
            return True, {
                "message": f"API Key {ctx.api_key[:8]}... has expired at {ctx.api_key_obj.expire_at}",
                "expire_at": ctx.api_key_obj.expire_at.isoformat()
            }
        
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        """过期的 Key 返回 401"""
        ctx.response_code = 401
        ctx.response_error = {
            "error": {
                "message": "Your API key has expired. Please renew your subscription.",
                "type": "auth_error",
                "code": "api_key_expired"
            }
        }


class ApiKeyBalanceStrategy(BaseRiskStrategy):
    """API Key 余额不足校验策略"""
    strategy_code = "api_key_balance_strategy"
    strategy_name = "API Key 余额不足校验"
    strategy_type = "key_health"
    default_priority = 12
    default_params = {
        "min_balance": 0.0  # 最低余额阈值
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        """检查 API Key 余额是否充足"""
        if not ctx.api_key_obj:
            return False, {}
        
        min_balance = self.params.get("min_balance", 0.0)
        
        # 检查余额是否低于阈值
        if ctx.api_key_obj.balance < min_balance:
            return True, {
                "message": f"API Key {ctx.api_key[:8]}... has insufficient balance: {ctx.api_key_obj.balance} (minimum: {min_balance})",
                "current_balance": float(ctx.api_key_obj.balance),
                "min_required": min_balance
            }
        
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        """余额不足的 Key 返回 402"""
        ctx.response_code = 402
        ctx.response_error = {
            "error": {
                "message": "Insufficient balance. Please top up your account to continue using the service.",
                "type": "payment_required",
                "code": "insufficient_balance",
                "param": "balance"
            }
        }
