from pathlib import Path, PureWindowsPath


class PathSecurityError(ValueError):
    pass


def resolve_runtime_path(runtime_root: Path, relative_path: str) -> Path:
    normalized = relative_path.strip()
    if not normalized:
        raise PathSecurityError("relative path cannot be empty")

    raw_path = PureWindowsPath(normalized)
    if raw_path.is_absolute():
        raise PathSecurityError("absolute paths are not allowed")

    if any(part in {"", ".", ".."} for part in raw_path.parts):
        raise PathSecurityError("unsafe relative path")

    return runtime_root / Path(*raw_path.parts)

