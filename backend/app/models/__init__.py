from app.models.env_check import EnvCheckResult
from app.models.health_check import HealthCheckConfig
from app.models.health_task import HealthTask
from app.models.profile_registry import ProfileRegistry
from app.models.repair_ticket import ManualRepairTicket
from app.models.run_log import TaskRunLog
from app.models.script_registry import ScriptRegistry
from app.models.script_run import ScriptRun
from app.models.session_task import SessionMaintenanceTask


def load_models() -> None:
    _ = (
        EnvCheckResult,
        HealthCheckConfig,
        HealthTask,
        ProfileRegistry,
        ManualRepairTicket,
        TaskRunLog,
        ScriptRegistry,
        ScriptRun,
        SessionMaintenanceTask,
    )
