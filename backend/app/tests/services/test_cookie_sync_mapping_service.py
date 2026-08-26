from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.errors import AppError
from app.models.cookie_sync_task import CookieSyncTask
from app.services.cookie_sync_mapping_service import CookieSyncMappingService


def _make_service(tmp_path: Path) -> tuple[CookieSyncMappingService, object]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'map.db'}")
    Base.metadata.create_all(engine)
    return CookieSyncMappingService(engine=engine), engine


def test_create_and_list_mapping(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)

    created = service.create_mapping(
        {
            "worker_id": "同事A",
            "domain": "Store.WeiXin.QQ.com",
            "channel": "weixin",
            "shop_name": "shop-a",
            "mobile_phone": "13900000002",
            "dns": "store.weixin.qq.com",
            "remark": "test",
        }
    )
    # domain 归一化为小写，channel 归一化为大写
    assert created["domain"] == "store.weixin.qq.com"
    assert created["channel"] == "WEIXIN"

    items = service.list_mappings()
    assert len(items) == 1
    assert items[0]["worker_id"] == "同事A"


def test_create_duplicate_raises_409(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    payload = {
        "worker_id": "同事A",
        "domain": "store.weixin.qq.com",
        "channel": "WEIXIN",
        "dns": "store.weixin.qq.com",
    }
    service.create_mapping(payload)

    with pytest.raises(AppError) as exc:
        service.create_mapping(payload)
    assert exc.value.status_code == 409
    assert exc.value.error_code == "DUPLICATE_MAPPING"


def test_update_mapping(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    created = service.create_mapping(
        {"worker_id": "同事A", "domain": "store.weixin.qq.com", "channel": "WEIXIN", "dns": "store.weixin.qq.com"}
    )

    updated = service.update_mapping(created["id"], {"remark": "改备注", "worker_id": "同事B"})

    assert updated["remark"] == "改备注"
    assert updated["worker_id"] == "同事B"


def test_delete_mapping(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    created = service.create_mapping(
        {"worker_id": "同事A", "domain": "store.weixin.qq.com", "channel": "WEIXIN", "dns": "store.weixin.qq.com"}
    )

    service.delete_mapping(created["id"])
    assert service.list_mappings() == []


def test_delete_mapping_blocked_when_task_depends(tmp_path: Path) -> None:
    """Spec REQ-008 AC-003：映射被采集任务依赖时删除被阻止。"""
    service, engine = _make_service(tmp_path)
    created = service.create_mapping(
        {
            "worker_id": "同事A",
            "domain": "store.weixin.qq.com",
            "channel": "WEIXIN",
            "shop_name": "shop-a",
            "mobile_phone": "13900000002",
            "dns": "store.weixin.qq.com",
        }
    )
    with Session(engine) as session:
        session.add(
            CookieSyncTask(
                cookie_sync_task_code="cst_dep001",
                cookie_sync_task_name="依赖任务",
                enabled=True,
                channel="WEIXIN",
                shop_name="shop-a",
                mobile_phone="13900000002",
                dns="store.weixin.qq.com",
                check_url="https://store.weixin.qq.com/check",
                http_method="GET",
            )
        )
        session.commit()

    with pytest.raises(AppError) as exc:
        service.delete_mapping(created["id"])
    assert exc.value.status_code == 409
    assert exc.value.error_code == "MAPPING_IN_USE"


def test_delete_mapping_blocked_only_for_enabled_tasks(tmp_path: Path) -> None:
    """停用的采集任务不阻止删除映射。"""
    service, engine = _make_service(tmp_path)
    created = service.create_mapping(
        {
            "worker_id": "同事A",
            "domain": "store.weixin.qq.com",
            "channel": "WEIXIN",
            "shop_name": "shop-a",
            "mobile_phone": "13900000002",
            "dns": "store.weixin.qq.com",
        }
    )
    with Session(engine) as session:
        session.add(
            CookieSyncTask(
                cookie_sync_task_code="cst_disabled001",
                cookie_sync_task_name="停用任务",
                enabled=False,
                channel="WEIXIN",
                shop_name="shop-a",
                mobile_phone="13900000002",
                dns="store.weixin.qq.com",
                check_url="https://store.weixin.qq.com/check",
                http_method="GET",
            )
        )
        session.commit()

    service.delete_mapping(created["id"])
    assert service.list_mappings() == []


def test_delete_mapping_not_found(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)

    with pytest.raises(AppError) as exc:
        service.delete_mapping(999)
    assert exc.value.status_code == 404
