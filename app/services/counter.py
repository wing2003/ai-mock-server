import asyncio
from collections import defaultdict
from datetime import datetime
from sqlalchemy import update
from app.core.database import AsyncSessionLocal
from app.models.base import ApiKey
from app.core.state import runtime_state
from app.services.config import config_service
import logging

logger = logging.getLogger(__name__)


class RequestCounterService:
    """
    高性能状态同步服务：内存缓存 + 异步批量落库
    
    - counters（请求计数）和 key_status_cache（状态变更）保存在内存中
    - 定时 flush 到数据库时，同时从 RuntimeState.keys 读取最新属性写入 DB
    - RuntimeState 为 None 时退化为仅操作 DB（兼容非运行时的 flush）
    """

    def __init__(self):
        # 内存中的请求计数：{api_key_str: count}
        self.counters = defaultdict(int)
        # 内存中的状态变更缓存：{api_key_str: status}
        self.key_status_cache = {}
        # 场景运行期间累计放行请求总数（flush 不清零）
        self._total_passed = 0
        self.is_running = False
        self.sync_task = None

    def increment(self, api_key: str):
        """内存中原子增加计数"""
        if self.is_running:
            self.counters[api_key] += 1
            self._total_passed += 1

    def get_total_passed(self) -> int:
        """获取场景运行期间累计放行的请求总数（跨 flush 不丢失）"""
        return self._total_passed

    def track_key_status(self, api_key: str, status: str):
        """记录 Key 的状态变更到内存缓存"""
        if self.is_running and api_key:
            current_status = self.key_status_cache.get(api_key)
            if current_status != status:
                self.key_status_cache[api_key] = status
                logger.debug(f"Tracked status change for key {api_key[:8]}... to {status}")

    async def start(self):
        self.is_running = True
        self._total_passed = 0  # 新场景启动时重置累计量
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
        """
        执行批量更新（计数与状态）。
        
        - 请求计数：按 api_key 字符串直接 SQL UPDATE，累计 total_requests
        - 状态变更：优先从 RuntimeState.keys 读取最新状态（内存实时同步过），
          若 RuntimeState 无数据则退回使用 key_status_cache 中的状态值
        """
        has_changes = False

        async with AsyncSessionLocal() as db:
            # 1. 同步请求计数（累计到 DB）
            if self.counters:
                logger.info(f"Flushing {len(self.counters)} API key request counts...")
                for api_key_str, count in self.counters.items():
                    stmt = (
                        update(ApiKey)
                        .where(ApiKey.api_key == api_key_str)
                        .values(total_requests=ApiKey.total_requests + count)
                    )
                    await db.execute(stmt)
                has_changes = True

            # 2. 同步状态变更
            if self.key_status_cache:
                logger.info(f"Flushing {len(self.key_status_cache)} API key status changes...")
                for api_key_str, cached_status in self.key_status_cache.items():
                    # 优先从 RuntimeState 内存读取最新状态（内存已通过 track_key_status/update_key 实时同步）
                    # 若 RuntimeState 无该 Key 则退回使用 key_status_cache 中的状态值
                    final_status = cached_status
                    key_obj = runtime_state.get_key_by_string(api_key_str)
                    if key_obj is not None:
                        final_status = key_obj.status  # 内存中的最新值

                    stmt = (
                        update(ApiKey)
                        .where(ApiKey.api_key == api_key_str)
                        .values(status=final_status, updated_at=datetime.utcnow())
                    )
                    await db.execute(stmt)
                    logger.debug(f"Flushed status for key {api_key_str[:8]}... -> {final_status}")
                has_changes = True

            if has_changes:
                await db.commit()
                logger.info("State data flushed successfully.")
                self.counters.clear()
                self.key_status_cache.clear()


# 全局单例
request_counter_service = RequestCounterService()
