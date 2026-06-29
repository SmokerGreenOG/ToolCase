from __future__ import annotations

__maker__ = "SmokerGreenOG"
import _protect

import json
import shutil
import time
from pathlib import Path
from typing import Any

from .report import risk_score, write_html
from .scanner import (
    apk_inventory,
    detect_frameworks,
    extract_apk,
    file_hashes,
    parse_manifest_text,
    scan_extracted_tree,
    validate_apk,
)
from .utils import command_exists, ensure_dir, run_command, sha256_file, write_json

OUTPUT_MARKER = ".apk_reverse_suite_output.json"


def _is_managed_output(out: Path) -> bool:
    marker = out / OUTPUT_MARKER
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return False
    return data.get("tool") == "apk_reverse_suite" and data.get("format_version") == 1


def _prepare_output_dirs(
    out: Path,
    names: set[str],
    apk: Path,
    *,
    cleanup_names: set[str] | None = None,
) -> dict[str, Path]:
    managed = _is_managed_output(out)
    all_names = names | (cleanup_names or set())
    paths = {name: out / name for name in all_names}

    for name, path in paths.items():
        if apk == path or path in apk.parents:
            raise ValueError(f"APK cannot be stored in managed output directory: {path}")
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError(f"Managed output path is not a normal directory: {path}")
        if path.exists() and not managed and any(path.iterdir()):
            raise ValueError(
                f"Refusing to overwrite existing directory not created by this tool: {path}"
            )

    for path in paths.values():
        if path.exists():
            shutil.rmtree(path)
    for name in names:
        paths[name].mkdir(parents=True)

    write_json(
        out / OUTPUT_MARKER,
        {"tool": "apk_reverse_suite", "format_version": 1},
    )
    return {name: paths[name] for name in names}


def analyze_apk(
    apk_path: str | Path,
    output_dir: str | Path,
    use_jadx: bool = False,
    use_apktool: bool = False,
) -> dict[str, Any]:
    apk = Path(apk_path).expanduser().resolve()
    if not apk.is_file():
        raise FileNotFoundError(f"APK not found: {apk}")
    if apk.suffix.lower() != ".apk":
        raise ValueError(f"Expected .apk file, got: {apk}")

    out = Path(output_dir).expanduser().resolve()
    validate_apk(apk, out / "extracted")
    out = ensure_dir(out)
    jadx_available = use_jadx and command_exists("jadx")
    apktool_available = use_apktool and command_exists("apktool")
    dir_names = {"extracted"}
    cleanup_names = {"jadx", "apktool"} if _is_managed_output(out) else set()
    if jadx_available:
        dir_names.add("jadx")
    if apktool_available:
        dir_names.add("apktool")
    output_dirs = _prepare_output_dirs(
        out,
        dir_names,
        apk,
        cleanup_names=cleanup_names,
    )

    extracted = output_dirs["extracted"]
    started = time.time()
    inventory = apk_inventory(apk)
    extract_apk(apk, extracted)

    tool_runs: dict[str, Any] = {}
    decoded_dirs = [extracted]

    if use_jadx:
        if jadx_available:
            jadx_dir = output_dirs["jadx"]
            tool_runs["jadx"] = run_command(["jadx", "-d", str(jadx_dir), str(apk)])
            if tool_runs["jadx"]["returncode"] == 0:
                decoded_dirs.insert(0, jadx_dir)
        else:
            tool_runs["jadx"] = {"available": False, "note": "jadx not found on PATH"}

    if use_apktool:
        if apktool_available:
            apktool_dir = output_dirs["apktool"]
            tool_runs["apktool"] = run_command(
                ["apktool", "d", "-f", str(apk), "-o", str(apktool_dir)]
            )
            if tool_runs["apktool"]["returncode"] == 0:
                decoded_dirs.insert(0, apktool_dir)
        else:
            tool_runs["apktool"] = {"available": False, "note": "apktool not found on PATH"}

    scan = scan_extracted_tree(extracted)
    manifest = parse_manifest_text(decoded_dirs)
    frameworks = detect_frameworks(inventory)

    report: dict[str, Any] = {
        "summary": "Static APK reverse-engineering analysis completed.",
        "metadata": {
            "apk_path": str(apk),
            "output_dir": str(out),
            "size_bytes": apk.stat().st_size,
            "sha256": sha256_file(apk),
            "duration_seconds": round(time.time() - started, 2),
        },
        "inventory": inventory,
        "frameworks": frameworks,
        "manifest": manifest,
        "scan": scan,
        "file_hashes": file_hashes(extracted),
        "tool_runs": tool_runs,
        "artifacts": {},
    }
    report["risk"] = risk_score(report)

    json_path = out / "report.json"
    html_path = out / "report.html"
    write_json(json_path, report)
    write_html(html_path, report)
    report["artifacts"] = {
        "json_report": str(json_path),
        "html_report": str(html_path),
        "extracted_dir": str(extracted),
    }
    write_json(json_path, report)
    return report
