from __future__ import annotations

import getpass
import os
from pathlib import Path

from app.core.config import get_settings


class DeployService:
    def __init__(self, *, runtime_root: Path) -> None:
        self.settings = get_settings()
        self.runtime_root = runtime_root

    def get_config(self) -> dict[str, object]:
        deploy_root = self.settings.deploy_root
        current_user = getpass.getuser()
        session_name = os.environ.get("SESSIONNAME", "").strip()
        current_user_hint = (
            f"当前运行用户为 {current_user}，检测到桌面会话 {session_name}。"
            if session_name
            else f"当前运行用户为 {current_user}，未检测到明确桌面会话，headed 模式脚本可能需要桌面环境。"
        )
        return {
            "deploy_root": str(deploy_root),
            "runtime_root": str(self.runtime_root),
            "startup_command": str(deploy_root / "start_backend.bat"),
            "api_host": self.settings.app_host,
            "api_port": self.settings.app_port,
            "current_user": current_user,
            "current_user_hint": current_user_hint,
            "directories": {
                "profiles": str(self.runtime_root / "profiles"),
                "scripts": str(self.runtime_root / "scripts"),
                "artifacts": str(self.runtime_root / "artifacts"),
                "logs": str(self.runtime_root / "logs"),
            },
        }
