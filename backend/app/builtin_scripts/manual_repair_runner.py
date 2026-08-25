from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    config_path = Path(sys.argv[1])
    config = json.loads(config_path.read_text(encoding="utf-8"))
    artifact_dir = Path(config["artifact_dir"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.joinpath("result.json").write_text(
        json.dumps({"status": "SUCCESS", "message": "browser opened"}),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
