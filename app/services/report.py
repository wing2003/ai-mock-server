from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.base import TestReport, RiskEvent, Scene, SceneStrategyRelation, StrategyMetadata
from app.core.database import AsyncSessionLocal
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

class ReportService:
    """测试报告服务"""

    async def generate_report(self, scene_id: int, started_at: datetime, total_passed: int = 0):
        """生成并保存测试报告
        
        Args:
            scene_id: 场景 ID
            started_at: 场景启动时间
            total_passed: 从 counter 服务捕获的放行请求总数
        """
        async with AsyncSessionLocal() as db:
            # 1. 获取场景信息
            scene_result = await db.execute(select(Scene).where(Scene.id == scene_id))
            scene = scene_result.scalar_one_or_none()
            if not scene:
                return None

            stopped_at = datetime.utcnow()
            duration = (stopped_at - started_at).total_seconds()

            # 2. 统计风控事件
            events_result = await db.execute(
                select(RiskEvent).where(
                    RiskEvent.scene_id == scene_id,
                    RiskEvent.created_at >= started_at
                )
            )
            events = events_result.scalars().all()

            blocked_requests = len(events)
            total_requests = total_passed + blocked_requests
            block_rate = blocked_requests / total_requests if total_requests > 0 else 0

            # 3. 聚合统计数据
            error_code_stats = {}
            strategy_trigger_stats = {}
            # 预加载 strategy_id -> strategy_code 映射
            strategy_name_map = {}
            if events:
                strategy_ids = list({e.strategy_id for e in events if e.strategy_id})
                if strategy_ids:
                    meta_result = await db.execute(
                        select(StrategyMetadata.id, StrategyMetadata.strategy_code).where(
                            StrategyMetadata.id.in_(strategy_ids)
                        )
                    )
                    for row in meta_result.all():
                        strategy_name_map[row[0]] = row[1]

            for event in events:
                code = str(event.error_code)
                error_code_stats[code] = error_code_stats.get(code, 0) + 1
                
                s_name = strategy_name_map.get(event.strategy_id, f"strategy_{event.strategy_id}")
                strategy_trigger_stats[s_name] = strategy_trigger_stats.get(s_name, 0) + 1

            # 4. 获取策略快照
            relations_result = await db.execute(
                select(SceneStrategyRelation, StrategyMetadata).join(
                    StrategyMetadata, SceneStrategyRelation.strategy_id == StrategyMetadata.id
                ).where(SceneStrategyRelation.scene_id == scene_id)
            )
            strategy_snapshot = []
            for rel, meta in relations_result.all():
                strategy_snapshot.append({
                    "name": meta.strategy_name,
                    "enabled": rel.is_enabled,
                    "params": rel.custom_params
                })

            # 5. 创建报告对象
            report = TestReport(
                scene_id=scene_id,
                scene_name=scene.name,
                scene_strategy_snapshot=strategy_snapshot,
                started_at=started_at,
                stopped_at=stopped_at,
                duration_seconds=int(duration),
                total_requests=total_requests,
                passed_requests=total_requests - blocked_requests,
                blocked_requests=blocked_requests,
                block_rate=round(block_rate, 4),
                error_code_stats=error_code_stats,
                strategy_trigger_stats=strategy_trigger_stats,
                top_events=[{
                    "type": e.event_type,
                    "key": e.api_key,
                    "time": e.created_at.isoformat()
                } for e in events[:10]]
            )
            
            db.add(report)
            await db.commit()
            await db.refresh(report)
            
            # 6. 回填事件中的 report_id
            for event in events:
                event.report_id = report.id
            await db.commit()
            
            logger.info(f"Report generated: ID {report.id} for scene {scene.name}")
            return report

# 全局单例
report_service = ReportService()
