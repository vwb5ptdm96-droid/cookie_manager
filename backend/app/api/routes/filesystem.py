from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Query

from app.core.response import success_response


router = APIRouter(tags=["filesystem"])


def _list_drives() -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for drive_letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        drive = f"{drive_letter}:\\"
        if os.path.exists(drive):
            items.append({"name": drive, "path": drive, "is_dir": True})
    return items


def _list_subdirs(path_str: str) -> list[dict[str, object]]:
    base = Path(path_str)
    if not base.is_dir():
        return []
    items: list[dict[str, object]] = []
    try:
        for entry in sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if entry.is_dir():
                items.append({"name": entry.name, "path": str(entry), "is_dir": True})
        # Also show files if needed — only dirs for now
    except PermissionError:
        pass
    return items


@router.get("/fs/list")
def list_directory(path: str = Query("", description="Directory path to list; empty = drive list")) -> dict[str, object]:
    if not path:
        return success_response({
            "current_path": "",
            "parent_path": None,
            "items": _list_drives(),
        })

    base = Path(path)
    if not base.exists():
        return success_response({"current_path": path, "parent_path": None, "items": []})
    if not base.is_dir():
        return success_response({"current_path": path, "parent_path": None, "items": []})

    parent = str(base.parent) if base.parent != base else None
    items = _list_subdirs(path)
    return success_response({
        "current_path": str(base),
        "parent_path": parent,
        "items": items,
    })
