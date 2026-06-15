import asyncio
from collections import defaultdict
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select
from app.core.database import AsyncSessionLocal
from app.models.base import ApiKey
from app.services.config import config_service
import logging

logger = logging.getLogger(__name__)

class RequestCounterService:
    """高性能状态同步服务：内存缓存 + 异步批量落库"""
    
    def __init__(self):
        self.counters = defaultdict(int)
        self.key_status_cache = {} # {api_key: status}
        self.is_running = False
        self.sync_task = None

    def increment(self, api_key: str):
        """内存中原子增加计数"""
        if self.is_running:
            self.counters[api_key] += 1

    def track_key_status(self, api_key: str, status: str):
        """记录 Key 的状态变更到内存缓存"""
        if self.is_running and api_key:
            current_status = self.key_status_cache.get(api_key)
            if current_status != status:
                self.key_status_cache[api_key] = status
                logger.debug(f"Tracked status change for key {api_key[:8]}... to {status}")

    async def start(self):
        self.is_running = True
        # 启动定时同步任务
        interval_str = await config_service.get_value("data_sync_interval", "30")
        interval = int(interval_str)
        self.sync_task = asyncio.create_task(self._sync_loop(interval))
        logger.info(f"State sync service started with sync interval {interval}s.")

    async def stop_and_flush(self):
        """停止服务并将内存数据刷入数据库"""
        self.is_running = False
        if self.sync_task:
            self.sync_task.cancel()
            try:
                await self.sync_task
            except asyncio.CancelledError:
                pass
        await self._flush_to_db()

    async def _sync_loop(self, interval: int):
        """定时同步循环"""
        while self.is_running:
            try:
                await asyncio.sleep(interval)
                await self._flush_to_db()
            except Exception as e:
                logger.error(f"Sync loop error: {e}")

    async def _flush_to_db(self):
        """执行批量更新（计数与状态）"""
        has_changes = False
        async with AsyncSessionLocal() as db:
            # 1. 同步请求计数
            if self.counters:
                logger.info(f"Flushing {len(self.counters)} API key request counts...")
                for api_key, count in self.counters.items():
                    stmt = update(ApiKey).where(ApiKey.api_key == api_key).values(
                        total_requests=ApiKey.total_requests + count
                    )
                    await db.execute(stmt)
                has_changes = True

            # 2. 同步状态变更
            if self.key_status_cache:
                logger.info(f"Flushing {len(self.key_status_cache)} API key status changes...")
                for api_key, status in self.key_status_cache.items():
                    stmt = update(ApiKey).where(ApiKey.api_key == api_key).values(
                        status=status,
                        updated_at=datetime.utcnow()
                    )
                    await db.execute(stmt)
                has_changes = True

            if has_changes:
                await db.commit()
                logger.info("State data flushed successfully.")
                self.counters.clear()
                self.key_status_cache.clear()

# 全局单例
request_counter_service = RequestCounterService()
