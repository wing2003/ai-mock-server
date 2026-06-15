from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    # 服务配置
    PORT: int = 8090
    HOST: str = "127.0.0.1"
    
    # 数据库类型：mysql 或 sqlite
    DB_TYPE: str = "mysql"
    
    # MySQL 数据库配置（DB_TYPE=mysql 时生效）
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "password"
    DB_NAME: str = "mock_risk_db"
    DB_POOL_SIZE: int = 5  # 减少连接池大小以避免过多连接
    DB_MAX_OVERFLOW: int = 10  # 减少最大溢出连接数
    
    # SQLite 配置（DB_TYPE=sqlite 时生效）
    SQLITE_PATH: str = "data/mock_risk.db"
    
    # 限流配置
    GLOBAL_RPM_LIMIT: int = 1000
    IP_RPM_LIMIT: int = 100
    KEY_RPM_LIMIT: int = 50
    
    # 安全配置
    SECRET_KEY: str = "your-secret-key-here"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # 异步任务并发数
    ASYNC_TASK_CONCURRENCY: int = 10

    class Config:
        env_file = ".env"

settings = Settings()

# 构建数据库 URL
def build_database_url() -> str:
    if settings.DB_TYPE == "sqlite":
        # SQLite 使用相对路径或绝对路径
        db_path = settings.SQLITE_PATH
        # 确保使用绝对路径，避免相对路径导致的连接问题
        if not os.path.isabs(db_path):
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), db_path)
        return f"sqlite+aiosqlite:///{db_path}"
    else:
        return f"mysql+asyncmy://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"

DATABASE_URL = build_database_url()

# 标识当前是否为 SQLite 模式
IS_SQLITE = settings.DB_TYPE == "sqlite"
