from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.deploy import router as deploy_router
from app.api.routes.environment import router as environment_router
from app.api.routes.health import router as health_router
from app.api.routes.health_checks import router as health_checks_router
from app.api.routes.health_tasks import router as health_tasks_router
from app.api.routes.logs import router as logs_router
from app.api.routes.profiles import router as profiles_router
from app.api.routes.repairs import router as repairs_router
from app.api.routes.script_runs import router as script_runs_router
from app.api.routes.session_tasks import router as session_tasks_router
from app.api.routes.scripts import router as scripts_router

__all__ = [
    "dashboard_router",
    "deploy_router",
    "environment_router",
    "health_router",
    "health_checks_router",
    "health_tasks_router",
    "logs_router",
    "profiles_router",
    "repairs_router",
    "script_runs_router",
    "scripts_router",
    "session_tasks_router",
]
