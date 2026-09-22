from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.core.database import Base
from app.core.errors import AppError
from app.services.sre_service import SreService, require_confirm


def _svc(tmp_path: Path) -> SreService:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'sre.db'}")
    Base.metadata.create_all(engine)
    return SreService(engine, tmp_path / "runtime", tmp_path, app_port=8081)


def test_require_confirm_blocks():
    with pytest.raises(AppError) as exc:
        require_confirm(False)
    assert exc.value.error_code == "SRE_GATE_REQUIRED"
    require_confirm(True)


def test_recycle_requires_confirm(tmp_path: Path):
    svc = _svc(tmp_path)
    with pytest.raises(AppError) as exc:
        svc.recycle_stale_runs(confirmed=False)
    assert exc.value.error_code == "SRE_GATE_REQUIRED"


def test_recycle_confirmed_returns_count(tmp_path: Path, monkeypatch):
    svc = _svc(tmp_path)
    monkeypatch.setattr(
        "app.services.health_task_service.HealthTaskService.reap_stale_runs",
        lambda self: 2,
    )
    out = svc.recycle_stale_runs(confirmed=True)
    assert out["reclaimed"] == 2
    audit = (tmp_path / "runtime" / "logs" / "sre-actions.jsonl").read_text(encoding="utf-8")
    assert "recycle_stale_runs" in audit


def test_restart_requires_confirm(tmp_path: Path):
    svc = _svc(tmp_path)
    with pytest.raises(AppError) as exc:
        svc.restart_backend(confirmed=False)
    assert exc.value.error_code == "SRE_GATE_REQUIRED"


def test_restart_dry_run_does_not_spawn(tmp_path: Path, monkeypatch):
    svc = _svc(tmp_path)
    spawned = []

    def fake_popen(*args, **kwargs):
        spawned.append(args)
        raise AssertionError("dry-run must not spawn")

    monkeypatch.setattr("app.services.sre_service.subprocess.Popen", fake_popen)
    monkeypatch.setattr(svc, "probe_health", lambda: {"ok": True, "status_code": 200})
    out = svc.restart_backend(confirmed=True, dry_run=True)
    assert out["dry_run"] is True
    assert out["scheduled"] is False
    assert spawned == []
    assert "restart_backend" in (tmp_path / "runtime" / "logs" / "sre-actions.jsonl").read_text(encoding="utf-8")
