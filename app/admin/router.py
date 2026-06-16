from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from app.core.database import get_db
from app.models.base import Scene, ApiKeyPool, ApiKey, ScenePoolRelation, StrategyMetadata, SceneStrategyRelation, TestReport, RiskEvent
from app.core.state import runtime_state
from app.services.healing import healing_service
from app.services.counter import request_counter_service
from app.services.report import report_service
from app.risk.scheduler import risk_scheduler  # noqa: F401  (re-exported for backward compat)

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/scenes", response_class=HTMLResponse)
async def list_scenes(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Scene).where(Scene.is_deleted == False))
        scenes = result.scalars().all()
        return request.app.state.templates.TemplateResponse(request, "scenes/list.html", {"scenes": scenes})
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error listing scenes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal service error: {str(e)}")

@router.post("/scenes/create")
async def create_scene(
    request: Request,
    name: str = Form(...),
    description: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    new_scene = Scene(name=name, description=description)
    db.add(new_scene)
    await db.commit()
    return RedirectResponse(url="/admin/scenes", status_code=303)

@router.post("/scenes/delete/{scene_id}")
async def delete_scene(scene_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Scene).where(Scene.id == scene_id))
    scene = result.scalar_one_or_none()
    if scene:
        scene.is_deleted = True
        await db.commit()
    return RedirectResponse(url="/admin/scenes", status_code=303)

@router.post("/scenes/start/{scene_id}")
async def start_scene(scene_id: int, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Scene).where(Scene.id == scene_id))
        scene = result.scalar_one_or_none()
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        
        if runtime_state.is_running:
            raise HTTPException(status_code=400, detail="Another scene is already running")
        
        scene.status = "running"
        scene.started_at = datetime.utcnow()
        await db.commit()
        
        # 一次性加载 Scene、Keys、Strategies 到内存（替代旧的 risk_scheduler.init_for_scene）
        await runtime_state.start_scene(scene_id, db)
        
        await healing_service.start()
        await request_counter_service.start()
        return RedirectResponse(url="/admin/scenes", status_code=303)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error starting scene {scene_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal service error: {str(e)}")

@router.post("/scenes/stop/{scene_id}")
async def stop_scene(scene_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Scene).where(Scene.id == scene_id))
    scene = result.scalar_one_or_none()
    if scene:
        scene.status = "stopped"
        stopped_at = datetime.utcnow()
        scene.stopped_at = stopped_at
        await db.commit()
    
    # 先捕获放行请求数，再 flush 并清空内存，确保数据不丢失
    total_passed = request_counter_service.get_total_passed()
    
    # 先 flush 再清空 RuntimeState 内存，确保 counter 的数据库写入先完成
    await healing_service.stop()
    await request_counter_service.stop_and_flush()
    runtime_state.stop_scene()
    
    # 生成测试报告
    if scene and scene.started_at:
        await report_service.generate_report(scene_id, scene.started_at, total_passed=total_passed)
    
    return RedirectResponse(url="/admin/reports", status_code=303)

@router.get("/reports", response_class=HTMLResponse)
async def list_reports(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TestReport).order_by(TestReport.created_at.desc()))
    reports = result.scalars().all()
    return request.app.state.templates.TemplateResponse(request, "reports/list.html", {"reports": reports})

@router.get("/reports/{report_id}", response_class=HTMLResponse)
async def view_report(request: Request, report_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TestReport).where(TestReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return request.app.state.templates.TemplateResponse(request, "reports/detail.html", {"report": report})

@router.get("/api/reports/{report_id}/export")
async def export_report(report_id: int, db: AsyncSession = Depends(get_db)):
    from openpyxl import Workbook
    from io import BytesIO
    from fastapi.responses import StreamingResponse
    
    result = await db.execute(select(TestReport).where(TestReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Test Report Summary"
    
    ws.append(["Metric", "Value"])
    ws.append(["Scene Name", report.scene_name])
    ws.append(["Started At", report.started_at.isoformat()])
    ws.append(["Stopped At", report.stopped_at.isoformat()])
    ws.append(["Duration (s)", report.duration_seconds])
    ws.append(["Total Requests", report.total_requests])
    ws.append(["Blocked Requests", report.blocked_requests])
    ws.append(["Block Rate", f"{report.block_rate * 100:.2f}%"])
    
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=report_{report_id}.xlsx"}
    )

@router.get("/pools", response_class=HTMLResponse)
async def list_pools(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ApiKeyPool).where(ApiKeyPool.is_deleted == False))
    pools = result.scalars().all()
    return request.app.state.templates.TemplateResponse(request, "pools/list.html", {"pools": pools})

@router.post("/pools/create")
async def create_pool(
    name: str = Form(...),
    description: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    new_pool = ApiKeyPool(name=name, description=description)
    db.add(new_pool)
    await db.commit()
    return RedirectResponse(url="/admin/pools", status_code=303)

@router.post("/pools/delete/{pool_id}")
async def delete_pool(pool_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ApiKeyPool).where(ApiKeyPool.id == pool_id))
    pool = result.scalar_one_or_none()
    if pool:
        pool.is_deleted = True
        await db.commit()
    return RedirectResponse(url="/admin/pools", status_code=303)

@router.get("/pools/{pool_id}/keys", response_class=HTMLResponse)
async def list_keys(request: Request, pool_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ApiKey).where(ApiKey.pool_id == pool_id, ApiKey.is_deleted == False))
    keys = result.scalars().all()
    pool_result = await db.execute(select(ApiKeyPool).where(ApiKeyPool.id == pool_id))
    pool = pool_result.scalar_one_or_none()
    return request.app.state.templates.TemplateResponse(request, "pools/keys.html", {"pool": pool, "keys": keys})

@router.post("/pools/{pool_id}/keys/generate")
async def generate_keys(
    pool_id: int,
    count: int = Form(10),
    prefix: str = Form("sk-"),
    balance: float = Form(0),
    db: AsyncSession = Depends(get_db)
):
    import uuid
    new_keys = []
    for _ in range(count):
        key_str = f"{prefix}{uuid.uuid4().hex}"
        new_keys.append(ApiKey(pool_id=pool_id, api_key=key_str, balance=balance))
    db.add_all(new_keys)
    await db.commit()
    return RedirectResponse(url=f"/admin/pools/{pool_id}/keys", status_code=303)

@router.post("/pools/keys/delete/{key_id}")
async def delete_key(key_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    key = result.scalar_one_or_none()
    if key:
        key.is_deleted = True
        await db.commit()
        # 同步 RuntimeState 内存（标记为已删除）
        runtime_state.update_key(key_id, is_deleted=True)
    return RedirectResponse(url=f"/admin/pools/{key.pool_id}/keys", status_code=303)

@router.post("/scenes/{scene_id}/pools/{pool_id}/bind")
async def bind_pool_to_scene(scene_id: int, pool_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScenePoolRelation).where(
        ScenePoolRelation.scene_id == scene_id,
        ScenePoolRelation.pool_id == pool_id
    ))
    if not result.scalar_one_or_none():
        relation = ScenePoolRelation(scene_id=scene_id, pool_id=pool_id)
        db.add(relation)
        await db.commit()
    return RedirectResponse(url=f"/admin/scenes/{scene_id}/config", status_code=303)

@router.post("/scenes/{scene_id}/pools/{pool_id}/unbind")
async def unbind_pool_from_scene(scene_id: int, pool_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScenePoolRelation).where(
        ScenePoolRelation.scene_id == scene_id,
        ScenePoolRelation.pool_id == pool_id
    ))
    relation = result.scalar_one_or_none()
    if relation:
        await db.delete(relation)
        await db.commit()
    return RedirectResponse(url=f"/admin/scenes/{scene_id}/config", status_code=303)

@router.get("/scenes/{scene_id}/config", response_class=HTMLResponse)
async def scene_config(request: Request, scene_id: int, db: AsyncSession = Depends(get_db)):
    scene_result = await db.execute(select(Scene).where(Scene.id == scene_id))
    scene = scene_result.scalar_one_or_none()
    
    # 获取所有可用的池
    pools_result = await db.execute(select(ApiKeyPool).where(ApiKeyPool.is_deleted == False))
    all_pools = pools_result.scalars().all()
    
    # 获取当前场景已绑定的池 ID
    pool_relations_result = await db.execute(select(ScenePoolRelation.pool_id).where(ScenePoolRelation.scene_id == scene_id))
    bound_pool_ids = {r[0] for r in pool_relations_result.all()}

    # 获取所有策略元数据（包括启用和禁用的）
    strategies_result = await db.execute(select(StrategyMetadata))
    all_strategies = strategies_result.scalars().all()
    
    # 按策略类型分组，并按优先级排序
    strategies_by_type = {}
    for strategy in all_strategies:
        stype = strategy.strategy_type
        if stype not in strategies_by_type:
            strategies_by_type[stype] = []
        strategies_by_type[stype].append(strategy)
    
    # 对每个类型的策略按优先级排序
    for stype in strategies_by_type:
        strategies_by_type[stype].sort(key=lambda s: s.default_priority)
    
    # 获取当前场景已绑定的策略关系
    strategy_relations_result = await db.execute(select(SceneStrategyRelation).where(SceneStrategyRelation.scene_id == scene_id))
    relations = {r.strategy_id: r for r in strategy_relations_result.scalars().all()}
    
    return request.app.state.templates.TemplateResponse(request, "scenes/config.html", {
        "scene": scene,
        "pools": all_pools,
        "bound_pool_ids": bound_pool_ids,
        "strategies_by_type": strategies_by_type,  # 按类型分组的策略
        "relations": relations
    })

@router.post("/scenes/{scene_id}/strategies/{strategy_id}/toggle")
async def toggle_scene_strategy(
    request: Request,
    scene_id: int,
    strategy_id: int,
    is_enabled: bool = Form(...),
    custom_params: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(SceneStrategyRelation).where(
        SceneStrategyRelation.scene_id == scene_id,
        SceneStrategyRelation.strategy_id == strategy_id
    ))
    relation = result.scalar_one_or_none()
    
    if relation:
        relation.is_enabled = is_enabled
        if custom_params:
            import json
            relation.custom_params = json.loads(custom_params)
    else:
        import json
        new_relation = SceneStrategyRelation(
            scene_id=scene_id,
            strategy_id=strategy_id,
            is_enabled=is_enabled,
            custom_params=json.loads(custom_params) if custom_params else {}
        )
        db.add(new_relation)
    
    await db.commit()
    
    # 获取策略详情用于渲染局部片段
    strategy_result = await db.execute(select(StrategyMetadata).where(StrategyMetadata.id == strategy_id))
    strategy = strategy_result.scalar_one_or_none()
    
    # 重新查询关系以获取最新状态
    new_relation_result = await db.execute(select(SceneStrategyRelation).where(
        SceneStrategyRelation.scene_id == scene_id,
        SceneStrategyRelation.strategy_id == strategy_id
    ))
    new_relation = new_relation_result.scalar_one_or_none()
    
    # 同步 RuntimeState：若当前场景正在运行且操作的就是该场景，实时更新内存中的策略列表
    if (runtime_state.is_running
            and runtime_state.scene
            and runtime_state.scene.id == scene_id
            and strategy):
        if is_enabled:
            # 启用：动态实例化策略并加入列表
            instance = runtime_state.load_strategy_instance(
                strategy,
                new_relation.custom_params if new_relation else {},
                strategy_id,
            )
            if instance:
                runtime_state.add_strategy(instance)
        else:
            # 禁用：从列表中移除
            runtime_state.remove_strategy(strategy.strategy_code)
    
    # 如果是 HTMX 请求，返回局部 HTML；否则重定向
    if request.headers.get("HX-Request"):
        return request.app.state.templates.TemplateResponse(request, "scenes/_strategy_row.html", {
            "strategy": strategy,
            "relation": new_relation,
            "request": request
        })
    return RedirectResponse(url=f"/admin/scenes/{scene_id}/config", status_code=303)

@router.post("/scenes/{scene_id}/strategies/{strategy_id}/params")
async def update_strategy_params(
    request: Request,
    scene_id: int,
    strategy_id: int,
    custom_params: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    import json
    try:
        params_dict = json.loads(custom_params) if custom_params else {}
    except:
        params_dict = {}

    result = await db.execute(select(SceneStrategyRelation).where(
        SceneStrategyRelation.scene_id == scene_id,
        SceneStrategyRelation.strategy_id == strategy_id
    ))
    relation = result.scalar_one_or_none()
    
    if relation:
        relation.custom_params = params_dict
    else:
        new_relation = SceneStrategyRelation(
            scene_id=scene_id,
            strategy_id=strategy_id,
            is_enabled=False,
            custom_params=params_dict
        )
        db.add(new_relation)
    
    await db.commit()
    
    # 返回局部片段
    strategy_result = await db.execute(select(StrategyMetadata).where(StrategyMetadata.id == strategy_id))
    strategy = strategy_result.scalar_one_or_none()
    
    new_relation_result = await db.execute(select(SceneStrategyRelation).where(
        SceneStrategyRelation.scene_id == scene_id,
        SceneStrategyRelation.strategy_id == strategy_id
    ))
    new_relation = new_relation_result.scalar_one_or_none()
    
    # 同步 RuntimeState：若当前场景正在运行且操作的就是该场景，刷新策略参数
    if (runtime_state.is_running
            and runtime_state.scene
            and runtime_state.scene.id == scene_id
            and strategy):
        runtime_state.update_strategy_params(strategy.strategy_code, params_dict)
    
    return request.app.state.templates.TemplateResponse(request, "scenes/_strategy_row.html", {
        "strategy": strategy,
        "relation": new_relation,
        "request": request
    })

@router.post("/pools/keys/update-status/{key_id}")
async def update_key_status(
    key_id: int,
    status: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    key = result.scalar_one_or_none()
    if key:
        key.status = status
        await db.commit()
        # 同步 RuntimeState 内存
        runtime_state.update_key(key_id, status=status)
    return RedirectResponse(url=f"/admin/pools/{key.pool_id}/keys", status_code=303)

@router.post("/pools/keys/update-balance/{key_id}")
async def update_key_balance(
    key_id: int,
    balance: float = Form(...),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    key = result.scalar_one_or_none()
    if key:
        key.balance = balance
        await db.commit()
        # 同步 RuntimeState 内存
        runtime_state.update_key(key_id, balance=balance)
    return RedirectResponse(url=f"/admin/pools/{key.pool_id}/keys", status_code=303)

@router.post("/pools/keys/reset-count/{key_id}")
async def reset_key_count(key_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    key = result.scalar_one_or_none()
    if key:
        key.total_requests = 0
        await db.commit()
    return RedirectResponse(url=f"/admin/pools/{key.pool_id}/keys", status_code=303)
