#!/usr/bin/env python3
"""
safe_delete.py — Central safe file/directory deletion for ToolCase v5.5.0.

Enforces:
  1. Resolved-path containment — target must be within workspace
  2. Audit logging — every deletion is recorded
  3. Dry-run support — preview without executing
  4. --force requirement for destructive operations

Usage:
    from safe_delete import safe_rmtree, safe_unlink
    safe_rmtree(path, workspace="/project", dry_run=False, force=True)
"""
from __future__ import annotations

__maker__ = "SmokerGreenOG"

import _protect

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

_AUDIT_LOG: Path | None = None


def _get_audit_log() -> logging.Logger:
    """Lazy-init audit logger — no file I/O on import."""
    global _AUDIT_LOG
    logger = logging.getLogger("safe_delete")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        _AUDIT_LOG = Path.home() / ".toolcase" / "logs" / "delete_audit.log"
        _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(str(_AUDIT_LOG), encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
    return logger


# ---------------------------------------------------------------------------
# Containment
# ---------------------------------------------------------------------------


def is_within_workspace(target: Path, workspace: Path) -> bool:
    """Check that resolved target is within resolved workspace."""
    try:
        target_resolved = target.resolve()
        ws_resolved = workspace.resolve()
        target_resolved.relative_to(ws_resolved)
        return True
    except (ValueError, OSError):
        return False


# ---------------------------------------------------------------------------
# Safe delete operations
# ---------------------------------------------------------------------------


def safe_rmtree(
    target: str | Path,
    *,
    workspace: str | Path | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Safely remove a directory tree.

    Args:
        target: Directory to remove.
        workspace: If set, target must be within this directory.
        dry_run: Preview only — log but don't delete.
        force: Required for actual deletion. Without it, returns blocked.

    Returns:
        dict with 'deleted', 'blocked', 'reason', 'path', 'dry_run'.
    """
    target_path = Path(target).resolve()
    result: dict[str, Any] = {
        "deleted": False,
        "blocked": False,
        "reason": "",
        "path": str(target_path),
        "dry_run": dry_run,
    }

    # ── Existence check ──────────────────────────────
    if not target_path.exists():
        result["reason"] = f"Path does not exist: {target_path}"
        return result

    # ── Workspace containment ────────────────────────
    if workspace is not None:
        ws = Path(workspace).resolve()
        if not is_within_workspace(target_path, ws):
            result["blocked"] = True
            result["reason"] = (
                f"Target outside workspace: {target_path} not within {ws}"
            )
            _get_audit_log().warning(
                "BLOCKED (containment): target=%s workspace=%s", target_path, ws
            )
            return result

    # ── Force requirement ────────────────────────────
    if not force and not dry_run:
        result["blocked"] = True
        result["reason"] = (
            f"Deletion requires --force flag. Use dry_run=True to preview."
        )
        _get_audit_log().warning("BLOCKED (no force): target=%s", target_path)
        return result

    # ── Dry run ──────────────────────────────────────
    if dry_run:
        # Count what would be deleted
        file_count = sum(1 for _ in target_path.rglob("*") if _.is_file())
        dir_count = sum(1 for _ in target_path.rglob("*") if _.is_dir())
        result["dry_run_preview"] = {
            "files": file_count,
            "dirs": dir_count,
            "total_size_bytes": sum(
                f.stat().st_size for f in target_path.rglob("*") if f.is_file()
            ),
        }
        _get_audit_log().info(
            "DRY-RUN: would delete %s (%d files, %d dirs)",
            target_path,
            file_count,
            dir_count,
        )
        return result

    # ── Execute deletion ─────────────────────────────
    try:
        shutil.rmtree(target_path)
        result["deleted"] = True
        result["reason"] = "Successfully deleted"
        _get_audit_log().info("DELETED: %s", target_path)
    except OSError as e:
        result["reason"] = f"Deletion failed: {e}"
        _get_audit_log().error("FAILED: %s — %s", target_path, e)

    return result


def safe_unlink(
    target: str | Path,
    *,
    workspace: str | Path | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Safely remove a single file.

    Same semantics as safe_rmtree but for individual files.
    """
    target_path = Path(target).resolve()
    result: dict[str, Any] = {
        "deleted": False,
        "blocked": False,
        "reason": "",
        "path": str(target_path),
        "dry_run": dry_run,
    }

    if not target_path.exists():
        result["reason"] = f"File does not exist: {target_path}"
        return result

    if target_path.is_dir():
        result["reason"] = f"Target is a directory, use safe_rmtree: {target_path}"
        return result

    if workspace is not None:
        ws = Path(workspace).resolve()
        if not is_within_workspace(target_path, ws):
            result["blocked"] = True
            result["reason"] = (
                f"Target outside workspace: {target_path} not within {ws}"
            )
            _get_audit_log().warning(
                "BLOCKED (containment): target=%s workspace=%s", target_path, ws
            )
            return result

    if not force and not dry_run:
        result["blocked"] = True
        result["reason"] = "Deletion requires --force flag."
        _get_audit_log().warning("BLOCKED (no force): target=%s", target_path)
        return result

    if dry_run:
        result["dry_run_preview"] = {
            "size_bytes": target_path.stat().st_size,
        }
        _get_audit_log().info("DRY-RUN: would delete %s", target_path)
        return result

    try:
        target_path.unlink()
        result["deleted"] = True
        result["reason"] = "Successfully deleted"
        _get_audit_log().info("DELETED: %s", target_path)
    except OSError as e:
        result["reason"] = f"Deletion failed: {e}"
        _get_audit_log().error("FAILED: %s — %s", target_path, e)

    return result
