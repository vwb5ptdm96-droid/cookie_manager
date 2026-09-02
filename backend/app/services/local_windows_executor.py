from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

from app.services.process_runner import ProcessRunResult, run_process


class LocalWindowsExecutor:
    def execute(
        self,
        *,
        script_path: Path,
        artifact_dir: Path,
        extra_env: dict[str, str] | None = None,
        run_id: str | None = None,
        control_file: str | None = None,
        timeout_seconds: int | None = None,
        on_start: Callable[[int], None] | None = None,
    ) -> dict[str, object]:
        stdout_path = artifact_dir / "stdout.log"
        stderr_path = artifact_dir / "stderr.log"
        log_path = artifact_dir / "run.log"
        result_path = artifact_dir / "result.json"

        artifact_dir.mkdir(parents=True, exist_ok=True)

        # 写入 control.json（初始状态：不暂停、不取消）
        control = {"pause": False, "cancel": False}
        if control_file:
            Path(control_file).write_text(
                json.dumps(control, ensure_ascii=False), encoding="utf-8"
            )
        else:
            control_file = str(artifact_dir / "control.json")
            Path(control_file).write_text(
                json.dumps(control, ensure_ascii=False), encoding="utf-8"
            )

        # 构建 config.json
        config = {
            "run_id": run_id or artifact_dir.name,
            "artifact_dir": str(artifact_dir),
            "control_file": control_file,
            "extra_env": extra_env or {},
        }
        config_path = artifact_dir / "config.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

        env = {
            "ARTIFACT_DIR": str(artifact_dir),
            "CONTROL_FILE": control_file,
        }
        if extra_env:
            env.update(extra_env)

        process_result: ProcessRunResult = run_process(
            command=[sys.executable, str(script_path)],
            cwd=script_path.parent,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            extra_env=env,
            timeout=timeout_seconds,
            on_start=on_start,
        )

        # 合并 stdout + stderr 到 run.log
        log_path.write_text(
            f"--- STDOUT ---\n{stdout_path.read_text(encoding='utf-8')}\n--- STDERR ---\n{stderr_path.read_text(encoding='utf-8')}",
            encoding="utf-8",
        )

        exit_code = process_result.exit_code

        if result_path.exists():
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            payload["exit_code"] = exit_code
        else:
            if process_result.timed_out:
                payload: dict[str, object] = {
                    "status": "FAIL",
                    "exit_code": exit_code,
                    "error_message": f"执行超时（>{timeout_seconds}s），已终止进程树",
                    "message": f"执行超时（>{timeout_seconds}s），已终止进程树",
                }
            else:
                payload: dict[str, object] = {
                    "status": "SUCCESS" if exit_code == 0 else "FAIL",
                    "exit_code": exit_code,
                }

        payload["pid"] = process_result.pid
        payload["stdout_path"] = process_result.stdout_path
        payload["stderr_path"] = process_result.stderr_path
        payload["log_path"] = str(log_path)
        payload["result_path"] = str(result_path)
        payload["control_file"] = control_file
        return payload
