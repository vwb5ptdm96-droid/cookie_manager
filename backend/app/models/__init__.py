from app.models.auto_repair_ticket import AutoRepairTicket
from app.models.auto_repair_shop_state import AutoRepairShopState
from app.models.cookie_sync_job import CookieSyncJob
from app.models.cookie_sync_mapping import CookieSyncMapping
from app.models.cookie_sync_task import CookieSyncTask
from app.models.env_check import EnvCheckResult
from app.models.health_task import HealthTask
from app.models.profile_registry import ProfileRegistry
from app.models.run_log import TaskRunLog
from app.models.script_registry import ScriptRegistry
from app.models.script_run import ScriptRun


def load_models() -> None:
    _ = (
        AutoRepairTicket,
        AutoRepairShopState,
        CookieSyncJob,
        CookieSyncMapping,
        CookieSyncTask,
        EnvCheckResult,
        HealthTask,
        ProfileRegistry,
        TaskRunLog,
        ScriptRegistry,
        ScriptRun,
    )
