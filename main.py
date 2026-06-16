from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import os
import logging
from dotenv import load_dotenv
from app.core.database import engine, Base
from app.core.state import runtime_state
from app.services.counter import request_counter_service
from app.services.config import config_service
from app.services.strategy_init import strategy_init_service
from app.risk.scheduler import risk_scheduler
from app.risk.context import RequestContext
import uuid

# 配置日志格式：包含时间戳
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 加载环境变量
load_dotenv()

def create_app() -> FastAPI:
    app = FastAPI(
        title="Mock API Risk Control System",
        description="Mock API 风控策略管理系统",
        version="1.0.0"
    )

    # 配置 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 全局中间件：拦截未启动场景的 Mock 请求并执行风控链
    @app.middleware("http")
    async def check_scene_status(request: Request, call_next):
        # 模型列表接口不需要场景运行状态，直接放行
        if request.url.path in ["/v1/models", "/v1beta/models"]:
            return await call_next(request)
        
        if request.url.path.startswith("/v1/"):
            if not runtime_state.is_running:
                return JSONResponse(
                    status_code=503,
                    content={"error": {"message": "Service Unavailable: No active scene running."}}
                )
            
            # 1. 提取请求特征
            auth_header = request.headers.get("authorization", "")
            api_key = None
            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:]
            else:
                api_key = request.headers.get("x-api-key") or request.headers.get("api-key")

            client_ip = request.client.host if request.client else "127.0.0.1"
            
            # 2. 构建请求上下文
            ctx = RequestContext(
                request_id=str(uuid.uuid4()),
                client_ip=client_ip,
                api_key=api_key,
                user_agent=request.headers.get("user-agent"),
                scene_id=runtime_state.scene.id if runtime_state.scene else None,
                request_path=request.url.path,
                request_method=request.method
            )

            # 3. API Key 基础校验：从 RuntimeState 内存读取，无需查数据库
            if api_key:
                key_obj = runtime_state.get_key_by_string(api_key)
                
                if not key_obj or key_obj.status != "active":
                    return JSONResponse(
                        status_code=401,
                        content={"error": {"message": "Invalid or inactive API Key."}}
                    )
                
                # 池绑定校验在启动时已通过（RuntimeState.keys 仅含绑定池的 Key），无需再查
                ctx.api_key_obj = key_obj

                # 4. 执行风控链
                is_risk = await risk_scheduler.execute_chain(ctx)
                if is_risk:
                    return JSONResponse(
                        status_code=429 if "limit" in ctx.trigger_strategy_code else 403,
                        content={"error": {"message": f"Risk control triggered: {ctx.trigger_details.get('message', 'Unknown')}"}}
                    )
                
                # 5. 内存计数
                request_counter_service.increment(api_key)

        response = await call_next(request)
        return response

    # 注册静态文件与模板
    if os.path.exists("static"):
        app.mount("/static", StaticFiles(directory="static"), name="static")
    
    templates = Jinja2Templates(directory="templates")
    app.state.templates = templates

    # 注册管理端路由（必须在 Mock 应用挂载之前注册，确保优先匹配）
    from app.admin.router import router as admin_router
    app.include_router(admin_router)

    # 根路径重定向到场景管理页面
    @app.get("/")
    async def root_redirect():
        return RedirectResponse(url="/admin/scenes", status_code=307)

    # favicon.ico 返回静态图片
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return FileResponse("static/favicon.jpg")

    # 注册原有 Mock 路由 (server.main)
    from server.main import app as mock_app
    
    # 将 Mock 应用挂载到根路径，所有未匹配的路由交给 Mock 应用处理
    app.mount("/", mock_app)

    return app

app = create_app()

@app.on_event("startup")
async def startup_event():
    # 自动建表：如果表不存在则创建
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logging.info("Database tables ensured (created if not exists).")
    await config_service.init_defaults()
    await strategy_init_service.init_default_strategies()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8090"))
    host = os.getenv("HOST", "127.0.0.1")
    logging.info(f"Starting server at {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
