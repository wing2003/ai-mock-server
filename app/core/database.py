from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import DATABASE_URL, IS_SQLITE, settings
import os
import logging

logger = logging.getLogger(__name__)

# SQLite 模式下确保数据目录存在
if IS_SQLITE:
    db_dir = os.path.dirname(DATABASE_URL.replace("sqlite+aiosqlite:///", ""))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        logger.info(f"Created SQLite data directory: {db_dir}")

# 创建异步引擎（根据数据库类型使用不同配置）
if IS_SQLITE:
    # SQLite 不支持连接池参数，使用简单配置
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        # SQLite 使用单连接，避免并发写入问题
        connect_args={"check_same_thread": False},
    )
    logger.info(f"SQLite async engine created: {DATABASE_URL}")
else:
    # MySQL 使用连接池配置
    engine = create_async_engine(
        DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,  # 在每次获取连接前检查连接是否有效
        pool_recycle=3600,   # 连接回收时间（秒），防止连接过期
        echo=False,  # 生产环境建议关闭 SQL 日志
    )
    logger.info("MySQL async engine created with connection pool.")

# 创建会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# 声明基类
Base = declarative_base()

async def get_db() -> AsyncSession:
    """获取数据库会话依赖"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()  # 确保事务提交
        except Exception as e:
            await session.rollback()  # 发生异常时回滚
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()
