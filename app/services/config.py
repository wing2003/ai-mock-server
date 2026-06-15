from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.base import GlobalConfig
import logging

logger = logging.getLogger(__name__)

class ConfigService:
    """全局配置服务"""
    
    @staticmethod
    async def get_value(name: str, default: str = None) -> str:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(GlobalConfig).where(GlobalConfig.name == name))
            config = result.scalar_one_or_none()
            return config.value if config else default

    @staticmethod
    async def set_value(name: str, value: str, value_type: str = "str", description: str = ""):
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(GlobalConfig).where(GlobalConfig.name == name))
            config = result.scalar_one_or_none()
            if config:
                config.value = value
            else:
                new_config = GlobalConfig(name=name, value=value, value_type=value_type, description=description)
                db.add(new_config)
            await db.commit()

    @staticmethod
    async def init_defaults():
        """初始化预设配置"""
        defaults = [
            {"name": "temp_limited_interval", "value": "300", "value_type": "int", "description": "临时限流时长，单位秒"},
            {"name": "data_sync_interval", "value": "30", "value_type": "int", "description": "状态数据定时同步到数据库的间隔时间，单位秒"},
            {"name": "healing_check_interval", "value": "60", "value_type": "int", "description": "自愈检查间隔，单位秒"}
        ]
        for item in defaults:
            await ConfigService.set_value(**item)
        logger.info("Global config defaults initialized.")

config_service = ConfigService()
