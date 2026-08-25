from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.path_utils import PathSecurityError, resolve_runtime_path
from app.models.script_registry import ScriptRegistry


class ScriptService:
    def __init__(self, engine: Engine, runtime_root: Path) -> None:
        self.engine = engine
        self.runtime_root = runtime_root

    def list_scripts(self) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            rows = session.execute(select(ScriptRegistry).order_by(ScriptRegistry.script_code.asc())).scalars().all()
        return [self._serialize(row) for row in rows]

    def upload(
        self,
        *,
        script_name: str,
        script_code: str,
        script_type: str,
        platform: str,
        version: str,
        description: str | None,
        filename: str,
        content: bytes,
        profile_key: str | None = None,
    ) -> dict[str, object]:
        script_name = script_name.strip()
        script_code = script_code.strip() if script_code else self._generate_code()
        script_type = script_type.strip()
        platform = platform.strip()
        version = version.strip() if version else "1.0.0"
        description = description.strip() if description else None
        main_file = self._sanitize_main_file(filename)

        self._validate_payload(
            script_name=script_name,
            script_code=script_code,
            script_type=script_type,
            platform=platform,
            version=version,
            main_file=main_file,
            content=content,
        )

        script_dir = "scripts"
        absolute_dir = resolve_runtime_path(self.runtime_root, script_dir)
        absolute_dir.mkdir(parents=True, exist_ok=True)
        (absolute_dir / main_file).write_bytes(content)

        with Session(self.engine) as session:
            row = session.execute(select(ScriptRegistry).where(ScriptRegistry.script_code == script_code)).scalar_one_or_none()

            if row is None:
                row = ScriptRegistry(
                    script_code=script_code,
                    script_name=script_name,
                    script_type=script_type,
                    platform=platform,
                    version=version,
                    profile_key=profile_key,
                    script_dir=script_dir,
                    main_file=main_file,
                    description=description,
                    enabled=True,
                )
                session.add(row)
            else:
                row.script_name = script_name
                row.script_type = script_type
                row.platform = platform
                row.version = version
                row.profile_key = profile_key
                row.script_dir = script_dir
                row.main_file = main_file
                row.description = description
                row.enabled = True

            session.commit()
            session.refresh(row)

        return self._serialize(row)

    def set_enabled(self, script_code: str, enabled: bool) -> dict[str, object]:
        with Session(self.engine) as session:
            row = session.execute(
                select(ScriptRegistry).where(ScriptRegistry.script_code == script_code)
            ).scalar_one_or_none()
            if row is None:
                raise AppError("脚本不存在", "SCRIPT_NOT_FOUND", status_code=404)
            row.enabled = enabled
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def delete_script(self, script_code: str) -> None:
        with Session(self.engine) as session:
            row = session.execute(
                select(ScriptRegistry).where(ScriptRegistry.script_code == script_code)
            ).scalar_one_or_none()
            if row is None:
                raise AppError("脚本不存在", "SCRIPT_NOT_FOUND", status_code=404)
            absolute_dir = resolve_runtime_path(self.runtime_root, row.script_dir)
            target = absolute_dir / row.main_file
            if target.is_file():
                target.unlink()
            session.delete(row)
            session.commit()

    def update_script(
        self, script_code: str, *, script_name: str | None = None,
        script_type: str | None = None, platform: str | None = None,
        description: str | None = None,
    ) -> dict[str, object]:
        with Session(self.engine) as session:
            row = session.execute(
                select(ScriptRegistry).where(ScriptRegistry.script_code == script_code)
            ).scalar_one_or_none()
            if row is None:
                raise AppError("脚本不存在", "SCRIPT_NOT_FOUND", status_code=404)
            if script_name is not None:
                row.script_name = script_name.strip()
            if script_type is not None:
                row.script_type = script_type.strip()
            if platform is not None:
                row.platform = platform.strip()
            if description is not None:
                row.description = description.strip() or None
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def clone_script(self, script_code: str) -> dict[str, object]:
        with Session(self.engine) as session:
            source = session.execute(
                select(ScriptRegistry).where(ScriptRegistry.script_code == script_code)
            ).scalar_one_or_none()
            if source is None:
                raise AppError("脚本不存在", "SCRIPT_NOT_FOUND", status_code=404)
            new_code = self._generate_code()
            row = ScriptRegistry(
                script_code=new_code,
                script_name=f"{source.script_name} (副本)",
                script_type=source.script_type,
                platform=source.platform,
                version=source.version,
                profile_key=source.profile_key,
                script_dir=source.script_dir,
                main_file=source.main_file,
                description=source.description,
                enabled=source.enabled,
                default_run_mode=source.default_run_mode,
                default_cdp_port=source.default_cdp_port,
                supports_pause=source.supports_pause,
                supports_cancel=source.supports_cancel,
                default_timeout_seconds=source.default_timeout_seconds,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def update_profile(self, script_code: str, profile_key: str | None) -> dict[str, object]:
        with Session(self.engine) as session:
            row = session.execute(
                select(ScriptRegistry).where(ScriptRegistry.script_code == script_code)
            ).scalar_one_or_none()
            if row is None:
                raise AppError("脚本不存在", "SCRIPT_NOT_FOUND", status_code=404)
            row.profile_key = profile_key
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def list_script_files(self, script_code: str) -> list[str]:
        with Session(self.engine) as session:
            row = session.execute(
                select(ScriptRegistry).where(ScriptRegistry.script_code == script_code)
            ).scalar_one_or_none()
            if row is None:
                raise AppError("脚本不存在", "SCRIPT_NOT_FOUND", status_code=404)
            absolute_dir = resolve_runtime_path(self.runtime_root, row.script_dir)
            if not absolute_dir.exists():
                return []
            return sorted(
                f.name for f in absolute_dir.iterdir()
                if f.is_file() and f.suffix.lower() == ".py"
            )

    def update_main_file(self, script_code: str, main_file: str) -> dict[str, object]:
        main_file = self._sanitize_main_file(main_file)
        with Session(self.engine) as session:
            row = session.execute(
                select(ScriptRegistry).where(ScriptRegistry.script_code == script_code)
            ).scalar_one_or_none()
            if row is None:
                raise AppError("脚本不存在", "SCRIPT_NOT_FOUND", status_code=404)
            absolute_dir = resolve_runtime_path(self.runtime_root, row.script_dir)
            if not (absolute_dir / main_file).is_file():
                raise AppError(f"文件 {main_file} 在脚本目录中不存在", "FILE_NOT_FOUND", status_code=404)
            row.main_file = main_file
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def _validate_payload(
        self,
        *,
        script_name: str,
        script_code: str,
        script_type: str,
        platform: str,
        version: str,
        main_file: str,
        content: bytes,
    ) -> None:
        if not script_name or not script_code or not version:
            raise AppError("脚本名称、编码和版本不能为空", "INVALID_SCRIPT_PACKAGE")
        if Path(main_file).suffix.lower() != ".py":
            raise AppError("当前仅支持上传 .py 脚本文件", "INVALID_SCRIPT_PACKAGE")
        if not content:
            raise AppError("脚本文件不能为空", "INVALID_SCRIPT_PACKAGE")

    def _sanitize_main_file(self, filename: str) -> str:
        main_file = Path(filename).name.strip()
        if not main_file:
            raise AppError("脚本文件名不能为空", "INVALID_SCRIPT_PACKAGE")
        if main_file in {".", ".."} or Path(main_file).name != main_file:
            raise AppError("脚本文件名非法", "INVALID_SCRIPT_PACKAGE")
        return main_file

    def _serialize(self, row: ScriptRegistry) -> dict[str, object]:
        absolute_dir = resolve_runtime_path(self.runtime_root, row.script_dir)
        return {
            "id": row.id,
            "script_code": row.script_code,
            "script_name": row.script_name,
            "script_type": row.script_type,
            "platform": row.platform,
            "version": row.version,
            "profile_key": row.profile_key,
            "script_dir": row.script_dir,
            "absolute_dir": str(absolute_dir),
            "main_file": row.main_file,
            "enabled": row.enabled,
            "default_run_mode": row.default_run_mode,
            "default_cdp_port": row.default_cdp_port,
            "supports_pause": row.supports_pause,
            "supports_cancel": row.supports_cancel,
            "default_timeout_seconds": row.default_timeout_seconds,
            "description": row.description,
            "updated_at": row.updated_at,
        }

    def update_run_config(
        self,
        script_code: str,
        *,
        default_run_mode: str | None = None,
        default_cdp_port: int | None = None,
        supports_pause: bool | None = None,
        supports_cancel: bool | None = None,
        default_timeout_seconds: int | None = None,
    ) -> dict[str, object]:
        with Session(self.engine) as session:
            row = session.execute(
                select(ScriptRegistry).where(ScriptRegistry.script_code == script_code)
            ).scalar_one_or_none()
            if row is None:
                raise AppError("脚本不存在", "SCRIPT_NOT_FOUND", status_code=404)
            if default_run_mode is not None:
                if default_run_mode not in ("HEADLESS", "HEADED"):
                    raise AppError("运行模式必须为 HEADLESS 或 HEADED", "INVALID_RUN_MODE")
                row.default_run_mode = default_run_mode
            if default_cdp_port is not None:
                if default_cdp_port < 1 or default_cdp_port > 65535:
                    raise AppError("CDP 端口必须在 1-65535 之间", "INVALID_CDP_PORT")
                row.default_cdp_port = default_cdp_port
            if supports_pause is not None:
                row.supports_pause = supports_pause
            if supports_cancel is not None:
                row.supports_cancel = supports_cancel
            if default_timeout_seconds is not None:
                if default_timeout_seconds < 1:
                    raise AppError("超时时间必须大于 0", "INVALID_TIMEOUT")
                row.default_timeout_seconds = default_timeout_seconds
            session.commit()
            session.refresh(row)
            return self._serialize(row)

    def check_cdp_ports(self) -> list[dict[str, object]]:
        """查询所有配置了 CDP 端口的脚本，检测端口是否被 Chrome 占用。"""
        import requests

        with Session(self.engine) as session:
            rows = session.execute(
                select(ScriptRegistry).where(
                    ScriptRegistry.default_cdp_port.isnot(None),
                )
            ).scalars().all()

        results: list[dict[str, object]] = []
        seen_ports: set[int] = set()
        for row in rows:
            port = row.default_cdp_port
            if port in seen_ports:
                continue
            seen_ports.add(port)

            in_use = False
            try:
                resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
                in_use = resp.status_code == 200
            except Exception:
                pass

            results.append({
                "port": port,
                "script_name": row.script_name,
                "script_code": row.script_code,
                "in_use": in_use,
            })

        return results

    @staticmethod
    def _generate_code() -> str:
        return f"script_{uuid4().hex[:10]}"
