from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.base import StrategyMetadata
import logging

logger = logging.getLogger(__name__)

class StrategyInitService:
    """策略元数据初始化服务"""
    
    @staticmethod
    async def init_default_strategies():
        """初始化系统内置的 8 大类风控策略"""
        strategies = [
            # 1. API Key 健康状态校验 (优先级 10-20)
            {"code": "api_key_ban_strategy", "name": "API Key 永久封禁校验", "type": "key_health", "priority": 10, "params": {}, "handler": "app.strategies.key_health.ApiKeyBanStrategy"},
            {"code": "api_key_expired_strategy", "name": "API Key 过期校验", "type": "key_health", "priority": 11, "params": {}, "handler": "app.strategies.key_health.ApiKeyExpiredStrategy"},
            {"code": "api_key_balance_strategy", "name": "API Key 余额不足校验", "type": "key_health", "priority": 12, "params": {}, "handler": "app.strategies.key_health.ApiKeyBalanceStrategy"},
            
            # 2. 网络与 IP 池风控 (优先级 21-40)
            {"code": "ip_rpm_limit", "name": "IP 每分钟请求数限制", "type": "network", "priority": 21, "params": {"rpm": 60}, "handler": "app.strategies.limit.IPRpmLimitStrategy"},
            {"code": "ip_rph_limit", "name": "IP 每小时请求数限制", "type": "network", "priority": 22, "params": {"rph": 1000}, "handler": "app.strategies.limit.IPRphLimitStrategy"},
            {"code": "ip_whitelist_strategy", "name": "IP 白名单校验", "type": "network", "priority": 23, "params": {}, "handler": "app.strategies.network.IPWhitelistStrategy"},
            
            # 3. 传输与指纹风控 (优先级 41-60)
            {"code": "ua_blacklist_check", "name": "User-Agent 黑名单校验", "type": "transport", "priority": 50, "params": {"blocked_uas": []}, "handler": "app.strategies.transport.UserAgentCheckStrategy"},
            
            # 4. 流量限流策略 (优先级 61-80)
            {"code": "global_rpm_limit", "name": "全局每分钟请求数限制", "type": "limit", "priority": 61, "params": {"rpm": 2000}, "handler": "app.strategies.limit.GlobalRpmLimitStrategy"},
            {"code": "api_key_rpm_limit", "name": "API Key 每分钟请求数限制", "type": "limit", "priority": 62, "params": {"rpm": 100}, "handler": "app.strategies.limit.ApiKeyRpmLimitStrategy"},
            {"code": "ip_concurrency_limit", "name": "单 IP 并发数限制", "type": "limit", "priority": 70, "params": {"max_concurrent": 10}, "handler": "app.strategies.limit.IPConcurrencyLimitStrategy"},
            {"code": "key_concurrency_limit", "name": "单 Key 并发数限制", "type": "limit", "priority": 71, "params": {"max_concurrent": 5}, "handler": "app.strategies.limit.KeyConcurrencyLimitStrategy"},
            
            # 5. 内容安全审核 (优先级 81-100)
            {"code": "content_safety_check", "name": "内容安全审核", "type": "content", "priority": 85, "params": {"block_level": [2, 3]}, "handler": "app.strategies.content.ContentSafetyStrategy"},
            
            # 6. 行为与业务风控 (优先级 101-120)
            {"code": "machine_behavior_check", "name": "机器匀速请求检测", "type": "behavior", "priority": 110, "params": {}, "handler": "app.strategies.behavior.MachineBehaviorStrategy"},
            
            # 7. 网络风控扩展 (优先级 21-40)
            {"code": "ip_key_relation_check", "name": "单 IP 多 Key 关联检测", "type": "network", "priority": 30, "params": {"max_keys_per_ip": 5}, "handler": "app.strategies.network.IPKeyRelationStrategy"},
            {"code": "key_ip_drift_check", "name": "单 Key 多 IP 漂移检测", "type": "network", "priority": 35, "params": {"max_ips_per_key": 3}, "handler": "app.strategies.network.KeyIPDriftStrategy"},
            
            # 7. 自动剔除与熔断 (优先级 121-140)
            {"code": "error_rate_fuse", "name": "错误率熔断", "type": "fuse", "priority": 121, "params": {"threshold": 0.5, "window": 60}, "handler": "app.strategies.fuse.ErrorRateFuseStrategy"},
            
            # 8. 自愈规则 (优先级 141-160)
            {"code": "auto_healing_rule", "name": "自动恢复规则", "type": "self_healing", "priority": 141, "params": {}, "handler": "app.strategies.healing.AutoHealingStrategy"}
        ]

        async with AsyncSessionLocal() as db:
            for s in strategies:
                result = await db.execute(select(StrategyMetadata).where(StrategyMetadata.strategy_code == s["code"]))
                if not result.scalar_one_or_none():
                    new_strategy = StrategyMetadata(
                        strategy_code=s["code"],
                        strategy_name=s["name"],
                        strategy_type=s["type"],
                        default_priority=s["priority"],
                        default_params=s["params"],
                        handler_class=s["handler"],
                        is_system=True,
                        is_enabled=True
                    )
                    db.add(new_strategy)
            await db.commit()
        logger.info("Default risk strategies initialized.")

strategy_init_service = StrategyInitService()
