from __future__ import annotations

__maker__ = "SmokerGreenOG"
import _protect

import json
from pathlib import Path
from typing import Any


def load_report(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compare_reports(old_report: dict[str, Any], new_report: dict[str, Any]) -> dict[str, Any]:
    def set_at(rep: dict[str, Any], section: str, key: str) -> set[str]:
        return set(rep.get(section, {}).get(key, []) or [])

    keys = [
        ("scan", "urls"),
        ("scan", "secrets"),
        ("scan", "risky_strings"),
        ("scan", "native_libs"),
        ("manifest", "permissions"),
        ("manifest", "suspicious_permissions"),
    ]
    out = {"added": {}, "removed": {}, "risk_delta": None}
    for section, key in keys:
        old = set_at(old_report, section, key)
        new = set_at(new_report, section, key)
        out["added"][f"{section}.{key}"] = sorted(new - old)
        out["removed"][f"{section}.{key}"] = sorted(old - new)
    old_score = old_report.get("risk", {}).get("score")
    new_score = new_report.get("risk", {}).get("score")
    if isinstance(old_score, int) and isinstance(new_score, int):
        out["risk_delta"] = new_score - old_score
    return out
