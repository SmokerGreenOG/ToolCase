from __future__ import annotations

__maker__ = "SmokerGreenOG"
import _protect

from pathlib import Path
from typing import Any

from .core.engine import analyze_apk


def run_toolcase_apk_reverse(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """
    ToolCase-friendly wrapper.

    Supported:
    run_toolcase_apk_reverse(apk_path="app.apk", output_dir="reports/app")
    run_toolcase_apk_reverse({"apk_path": "app.apk", "output_dir": "reports/app"})
    """
    payload: dict[str, Any] = {}
    if args and isinstance(args[0], dict):
        payload.update(args[0])
    payload.update(kwargs)

    apk_path = payload.get("apk_path") or payload.get("apk")
    output_dir = payload.get("output_dir") or payload.get("out")
    if not apk_path:
        raise ValueError("Missing apk_path")
    if not output_dir:
        apk_name = Path(apk_path).stem
        output_dir = str(Path("reports") / f"apk_{apk_name}")

    return analyze_apk(
        apk_path=apk_path,
        output_dir=output_dir,
        use_jadx=bool(payload.get("use_jadx", False)),
        use_apktool=bool(payload.get("use_apktool", False)),
    )
