from pathlib import Path

import pytest

from app.core.path_utils import PathSecurityError, resolve_runtime_path


def test_resolve_runtime_path_returns_absolute_path_under_runtime_root():
    runtime_root = Path(r"D:\session-maintenance-system\runtime")

    result = resolve_runtime_path(runtime_root, r"profiles\profile_ks_138\current")

    assert result == runtime_root / "profiles" / "profile_ks_138" / "current"


@pytest.mark.parametrize(
    "relative_path",
    [
        r"..\profiles\profile_ks_138\current",
        r"profiles\..\..\Windows\System32",
        r"C:\Windows\System32",
        r"\\server\share",
        "",
    ],
)
def test_resolve_runtime_path_rejects_unsafe_path(relative_path: str):
    runtime_root = Path(r"D:\session-maintenance-system\runtime")

    with pytest.raises(PathSecurityError):
        resolve_runtime_path(runtime_root, relative_path)

