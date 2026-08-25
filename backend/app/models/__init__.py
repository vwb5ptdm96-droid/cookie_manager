from app.models.env_check import EnvCheckResult
from app.models.health_task import HealthTask
from app.models.profile_registry import ProfileRegistry
from app.models.run_log import TaskRunLog
from app.models.script_registry import ScriptRegistry
from app.models.script_run import ScriptRun


def load_models() -> None:
    _ = (
        EnvCheckResult,
        HealthTask,
        ProfileRegistry,
        TaskRunLog,
        ScriptRegistry,
        ScriptRun,
    )
