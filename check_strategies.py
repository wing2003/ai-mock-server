import asyncio
from app.core.database import AsyncSessionLocal
from app.models.base import StrategyMetadata
from sqlalchemy import select

async def check_strategies():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(StrategyMetadata))
        strategies = result.scalars().all()
        
        print("=" * 100)
        print("数据库中已注册的策略列表")
        print("=" * 100)
        print(f"{'策略代码':<35} {'启用状态':<8} {'处理器路径'}")
        print("-" * 100)
        
        for s in sorted(strategies, key=lambda x: x.default_priority):
            status = "✅" if s.is_enabled else "❌"
            print(f"{s.strategy_code:<35} {status:<8} {s.handler_class}")
        
        print(f"\n总计: {len(strategies)} 个策略")

if __name__ == "__main__":
    asyncio.run(check_strategies())
