import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.deploy import router as deploy_router
from app.api.routes.environment import router as environment_router
from app.api.routes.filesystem import router as filesystem_router
from app.api.routes.health_tasks import router as health_tasks_router
from app.api.routes.profiles import router as profiles_router
from app.api.routes.health import router as health_router
from app.api.routes.logs import router as logs_router
from app.api.routes.script_runs import router as script_runs_router
from app.api.routes.scripts import router as scripts_router
from app.api.deps import get_engine
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.response import error_response
from app.models import load_models
from app.services.scheduler_service import HealthTaskScheduler


settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = None
    if os.getenv("PYTEST_CURRENT_TEST"):
        yield
        return

    scheduler = HealthTaskScheduler(engine=get_engine(), runtime_root=settings.runtime_root)
    scheduler.start()
    app.state.scheduler_service = scheduler
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown()
            app.state.scheduler_service = None


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.state.runtime_root = settings.runtime_root
load_models()
app.include_router(health_router, prefix="/api")
app.include_router(environment_router, prefix="/api")
app.include_router(deploy_router, prefix="/api")
app.include_router(health_tasks_router, prefix="/api")
app.include_router(logs_router, prefix="/api")
app.include_router(profiles_router, prefix="/api")
app.include_router(filesystem_router, prefix="/api")
app.include_router(script_runs_router, prefix="/api")
app.include_router(scripts_router, prefix="/api")


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc.message, exc.error_code),
    )


# ── 前端静态文件 ──
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="frontend_assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        # 只处理非 /api 的路由
        if full_path.startswith("api/") or full_path.startswith("openapi"):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        from fastapi.responses import FileResponse
        return FileResponse(str(_frontend_dist / "index.html"))
