from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.core.database import Base
from app.core.errors import AppError
from app.services.script_service import ScriptService


def build_service(tmp_path: Path) -> ScriptService:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'scripts.db'}")
    Base.metadata.create_all(engine)
    return ScriptService(engine=engine, runtime_root=tmp_path / "runtime")


def test_script_service_uploads_valid_python_script(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    result = service.upload(
        script_name="快手维护脚本",
        script_code="maintain_ks",
        script_type="MAINTAIN",
        platform="KUAISHOU",
        version="1.0.0",
        description="demo script",
        filename="main.py",
        content=b"print('hello')\n",
    )

    assert result["script_code"] == "maintain_ks"
    assert result["main_file"] == "main.py"
    assert result["script_dir"] == "scripts/uploaded/maintain_ks/1.0.0"
    assert result["absolute_dir"].endswith("runtime\\scripts\\uploaded\\maintain_ks\\1.0.0")
    assert (tmp_path / "runtime" / "scripts" / "uploaded" / "maintain_ks" / "1.0.0" / "main.py").exists()


def test_script_service_rejects_non_python_file(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    with pytest.raises(AppError) as exc_info:
        service.upload(
            script_name="bad script",
            script_code="bad_script",
            script_type="MAINTAIN",
            platform="COMMON",
            version="1.0.0",
            description=None,
            filename="bad_script.zip",
            content=b"zip-data",
        )

    assert exc_info.value.error_code == "INVALID_SCRIPT_PACKAGE"


def test_script_service_rejects_empty_script_name(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    with pytest.raises(AppError) as exc_info:
        service.upload(
            script_name="",
            script_code="bad_script",
            script_type="MAINTAIN",
            platform="COMMON",
            version="1.0.0",
            description=None,
            filename="main.py",
            content=b"print('hello')\n",
        )

    assert exc_info.value.error_code == "INVALID_SCRIPT_PACKAGE"
