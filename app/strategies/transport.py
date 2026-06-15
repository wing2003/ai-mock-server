from typing import Tuple, Dict, Any
from app.strategies.base import BaseRiskStrategy
from app.risk.context import RequestContext

class UserAgentCheckStrategy(BaseRiskStrategy):
    strategy_code = "ua_blacklist_check"
    strategy_name = "User-Agent 黑名单校验"
    strategy_type = "transport"
    default_priority = 50
    default_params = {
        "blocked_uas": ["python-requests/2.31.0", "curl/7.68.0"]  # 示例黑名单
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        if not ctx.user_agent:
            return False, {}
        
        blocked_uas = self.params.get("blocked_uas", [])
        for ua in blocked_uas:
            if ua.lower() in ctx.user_agent.lower():
                return True, {"matched_ua": ua}
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        ctx.response_code = 403
        ctx.response_error = {
            "error": {
                "message": "Access denied due to User-Agent restriction.",
                "type": "transport_risk",
                "code": "ua_blocked"
            }
        }


class TLSFingerprintStrategy(BaseRiskStrategy):
    """TLS/JA3 指纹匹配策略"""
    strategy_code = "tls_fingerprint_check"
    strategy_name = "TLS/JA3 指纹匹配"
    strategy_type = "transport"
    default_priority = 45
    default_params = {
        "blocked_ja3_hashes": []  # 黑名单 JA3 指纹哈希列表
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        """检查 TLS 指纹是否在黑名单中"""
        if not ctx.tls_fingerprint:
            return False, {}
        
        blocked_hashes = self.params.get("blocked_ja3_hashes", [])
        
        # 如果没有配置黑名单，不拦截
        if not blocked_hashes:
            return False, {}
        
        # 检查指纹是否匹配黑名单
        if ctx.tls_fingerprint in blocked_hashes:
            return True, {
                "message": f"TLS fingerprint {ctx.tls_fingerprint[:16]}... is blocked",
                "ja3_hash": ctx.tls_fingerprint,
                "matched": True
            }
        
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        """TLS 指纹匹配黑名单，返回 403"""
        ctx.response_code = 403
        ctx.response_error = {
            "error": {
                "message": "Access denied. Your client's TLS fingerprint has been blocked.",
                "type": "transport_risk",
                "code": "tls_fingerprint_blocked"
            }
        }


class UserAgentStrategy(BaseRiskStrategy):
    """User-Agent 白名单/强制要求策略"""
    strategy_code = "user_agent_check"
    strategy_name = "User-Agent 规范检测"
    strategy_type = "transport"
    default_priority = 48
    default_params = {
        "required_uas": [],  # 必须包含的 UA 特征
        "mode": "whitelist"  # whitelist: 白名单模式; blacklist: 黑名单模式
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        """检查 User-Agent 是否符合规范"""
        if not ctx.user_agent:
            # 如果没有 UA，根据配置决定是否拦截
            required_uas = self.params.get("required_uas", [])
            if required_uas:
                return True, {
                    "message": "Missing required User-Agent header",
                    "has_ua": False
                }
            return False, {}
        
        mode = self.params.get("mode", "whitelist")
        required_uas = self.params.get("required_uas", [])
        
        if mode == "whitelist" and required_uas:
            # 白名单模式：UA 必须包含至少一个要求的特征
            matched = any(req.lower() in ctx.user_agent.lower() for req in required_uas)
            if not matched:
                return True, {
                    "message": f"User-Agent does not match whitelist requirements",
                    "current_ua": ctx.user_agent[:50],
                    "required_patterns": required_uas
                }
        
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        """UA 不符合规范，返回 403"""
        ctx.response_code = 403
        ctx.response_error = {
            "error": {
                "message": "Invalid or missing User-Agent. Please use an authorized client.",
                "type": "transport_risk",
                "code": "invalid_user_agent"
            }
        }
