import asyncio
from datetime import datetime, timedelta
from sqlalchemy import update
from app.core.database import AsyncSessionLocal
from app.models.base import ApiKey
from app.core.state import runtime_state
from app.services.config import config_service
import logging

logger = logging.getLogger(__name__)


class HealingService:
    """
    自愈服务（全局单例）：定时检查并恢复受限的 API Key
    
    - 优先从 RuntimeState.keys 内存读取待自愈的 Key，避免查库
    - 自愈后同时更新 RuntimeState 内存和数据库
    - RuntimeState 未运行时跳过本轮自愈
    """

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
        """
        执行具体的自愈逻辑：
        1. 遍历 RuntimeState.keys，找出处于 temp_limited / ip_risk / node_unavailable
           状态且冷却期已过的 Key
        2. 将这些 Key 恢复为 active，同时更新 RuntimeState 内存和数据库
        3. 清理 ip_key_map / key_ip_map 中对应的关联记录
        """
        from app.strategies.network import ip_key_map, key_ip_map

        # RuntimeState 未运行时直接跳过
        if not runtime_state.is_running:
            return

        now = datetime.utcnow()

        # 1. 获取冷却期阈值
        interval_str = await config_service.get_value("temp_limited_interval", "300")
        interval = int(interval_str)
        cooldown_time = now - timedelta(seconds=interval)

        # 2. 从 RuntimeState 内存找出待自愈的 Key（取快照副本，避免并发清空 dict 时报错）
        keys_snapshot = list(runtime_state.keys.values())
        keys_to_heal = []
        node_keys_to_heal = []
        for key_obj in keys_snapshot:
            if key_obj.updated_at is None:
                continue
            if key_obj.status in ("temp_limited", "ip_risk") and key_obj.updated_at <= cooldown_time:
                keys_to_heal.append(key_obj)
            elif key_obj.status == "node_unavailable" and key_obj.updated_at <= cooldown_time:
                node_keys_to_heal.append(key_obj)

        healed_keys = []
        async with AsyncSessionLocal() as db:
            # 3. 处理临时限流和 IP 关联风险
            for key in keys_to_heal:
                logger.info(f"Auto-healing API Key from {key.status}: {key.api_key[:8]}...")
                api_key_str = key.api_key

                # 更新 RuntimeState 内存
                runtime_state.update_key(key.id, status="active", updated_at=now)

                # 更新数据库
                stmt = (
                    update(ApiKey)
                    .where(ApiKey.id == key.id)
                    .values(status="active", updated_at=now)
                )
                await db.execute(stmt)

                # 清理 IP-Key 关联映射
                ips_to_clean = []
                for ip, keys_dict in ip_key_map.items():
                    if api_key_str in keys_dict:
                        del keys_dict[api_key_str]
                        logger.debug(f"Cleaned key {api_key_str[:8]}... from ip_key_map for IP {ip}")
                        if not keys_dict:
                            ips_to_clean.append(ip)

                for ip in ips_to_clean:
                    del ip_key_map[ip]
                    logger.debug(f"Removed empty IP record from ip_key_map: {ip}")

                if api_key_str in key_ip_map:
                    del key_ip_map[api_key_str]
                    logger.debug(f"Removed key {api_key_str[:8]}... from key_ip_map")

                healed_keys.append(key)

            # 4. 处理节点不可用 - 试探性恢复
            for key in node_keys_to_heal:
                logger.info(f"Auto-healing node_unavailable API Key: {key.api_key[:8]}...")
                runtime_state.update_key(key.id, status="active", updated_at=now)
                stmt = (
                    update(ApiKey)
                    .where(ApiKey.id == key.id)
                    .values(status="active", updated_at=now)
                )
                await db.execute(stmt)
                healed_keys.append(key)

            if healed_keys:
                await db.commit()
                logger.info(f"Successfully healed {len(healed_keys)} API Keys.")


# 全局单例
healing_service = HealingService()
