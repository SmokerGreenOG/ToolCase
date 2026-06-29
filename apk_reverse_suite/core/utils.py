from __future__ import annotations

__maker__ = "SmokerGreenOG"
import _protect

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from safe_run import safe_run as _safe_run_exec


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(cmd: list[str], cwd: Path | None = None, timeout: int = 600) -> dict[str, Any]:
    try:
        result = _safe_run_exec(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            risk_level="medium",
        )
        if result.blocked:
            return {
                "cmd": cmd,
                "returncode": -1,
                "stdout": result.stdout or "",
                "stderr": result.block_reason or result.stderr or "",
            }
        return {
            "cmd": cmd,
            "returncode": result.returncode,
            "stdout": result.stdout[-8000:] if result.stdout else "",
            "stderr": result.stderr[-8000:] if result.stderr else "",
        }
    except TimeoutError as exc:
        return {"cmd": cmd, "returncode": -1, "stdout": "", "stderr": f"Timeout: {exc}"}
    except OSError as exc:
        return {"cmd": cmd, "returncode": -1, "stdout": "", "stderr": f"Execution failed: {exc}"}


def safe_relpath(path: Path, root: Path) -> str:
    return os.path.relpath(str(path), str(root)).replace(os.sep, "/")
