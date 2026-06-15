from limits import storage, strategies, RateLimitItemPerMinute, RateLimitItemPerHour
from app.services.config import config_service
import logging

logger = logging.getLogger(__name__)

class AsyncLimiter:
    """基于 limits 库的工业级异步限流器"""
    
    def __init__(self):
        # 使用内存存储，适配单实例场景
        self.storage = storage.MemoryStorage()
        self.strategy = strategies.MovingWindowRateLimiter(self.storage)

    async def is_rate_limited(self, key: str, limit: int, period: int = 60) -> bool:
        """
        检查是否触发限流
        :param key: 限流键 (如 ip:xxx, key:xxx)
        :param limit: 限制次数
        :param period: 周期（秒）
        :return: True 表示被限流
        """
        try:
            if period == 3600:
                item = RateLimitItemPerHour(limit)
            else:
                item = RateLimitItemPerMinute(limit)
            
            # limits 库的 hit 方法返回 False 表示被限流（即超过限制）
            allowed = self.strategy.hit(item, key)
            logger.debug(f"Rate limit check for {key}: limit={limit}, period={period}s, allowed={allowed}")
            return not allowed
        except Exception as e:
            logger.error(f"Rate limit check error for key {key}: {e}")
            return False

# 全局单例
limiter = AsyncLimiter()
