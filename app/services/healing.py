import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.base import ApiKey
from app.services.config import config_service
import logging

logger = logging.getLogger(__name__)

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
        while self.is_running:
            try:
                await self._check_and_heal()
            except Exception as e:
                logger.error(f"Healing loop error: {e}")
            # 等待 60 秒后再次执行
            await asyncio.sleep(60)

    async def _check_and_heal(self):
        """执行具体的自愈逻辑"""
        from app.strategies.network import ip_key_map, key_ip_map
        
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
                
                # 清理该 Key 在 IP-Key 关联映射中的记录
                api_key = key.api_key
                # 从 ip_key_map 中删除该 key 的所有记录
                ips_to_clean = []
                for ip, keys_dict in ip_key_map.items():
                    if api_key in keys_dict:
                        del keys_dict[api_key]
                        logger.debug(f"Cleaned key {api_key[:8]}... from ip_key_map for IP {ip}")
                        # 如果该 IP 下没有其他 key 了，也删除该 IP 的记录
                        if not keys_dict:
                            ips_to_clean.append(ip)
                
                for ip in ips_to_clean:
                    del ip_key_map[ip]
                    logger.debug(f"Removed empty IP record from ip_key_map: {ip}")
                
                # 从 key_ip_map 中删除该 key 的记录
                if api_key in key_ip_map:
                    del key_ip_map[api_key]
                    logger.debug(f"Removed key {api_key[:8]}... from key_ip_map")
            
            # 2. 处理节点不可用 (node_unavailable) - 试探性恢复
            node_result = await db.execute(
                select(ApiKey).where(
                    ApiKey.status == "node_unavailable",
                    ApiKey.updated_at <= cooldown_time
                )
            )
            node_keys = node_result.scalars().all()
            for key in node_keys:
                key.status = "active" # 尝试恢复

            if keys_to_heal or node_keys:
                await db.commit()
                logger.info(f"Successfully healed {len(keys_to_heal) + len(node_keys)} API Keys.")

# 全局单例
healing_service = HealingService()
