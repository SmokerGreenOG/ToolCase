"""ToolCase shared core utilities — internal package for cross-tool helpers.

This module provides commonly duplicated functions used across multiple ToolCase tools.
Import from here instead of re-implementing in each tool.

Usage:
    from toolcase_core.utils import normalize_url, collect_source_files
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Default extension sets used by various scanners
# ---------------------------------------------------------------------------

WEB_EXTENSIONS: frozenset[str] = frozenset(
    {".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".mjs", ".cjs"}
)

PYTHON_EXTENSIONS: frozenset[str] = frozenset({".py", ".pyi"})

# ---------------------------------------------------------------------------
# Default exclusion directories
# ---------------------------------------------------------------------------

DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        "__pycache__",
        "node_modules",
        ".git",
        ".venv",
        "venv",
        ".tox",
        ".eggs",
        "build",
        "dist",
        ".rsi_backups",
        ".rsi_reports",
        ".self_improve_reports",
        ".backups",
        "*.egg-info",
    }
)

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def normalize_url(url: str) -> str:
    """Normalize a route URL: strip query string, trailing slash, collapse //."""
    url = url.split("?")[0]
    url = url.rstrip("/")
    while "//" in url:
        url = url.replace("//", "/")
    return url


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def collect_source_files(
    root: Path,
    *,
    extensions: frozenset[str] = WEB_EXTENSIONS,
    exclude_dirs: frozenset[str] = DEFAULT_EXCLUDE_DIRS,
    sort: bool = True,
) -> list[Path]:
    """Collect source files recursively, skipping excluded directories.

    Args:
        root: Directory or single file to scan.
        extensions: File extensions to include (with dot, e.g. '.py').
        exclude_dirs: Directory names to skip.
        sort: Return sorted list (deterministic ordering).

    Returns:
        List of matching Path objects.
    """
    if not root.exists():
        return []

    if root.is_file():
        return [root] if root.suffix.lower() in extensions else []

    files: list[Path] = []
    for fp in root.rglob("*"):
        # Skip excluded directories
        rel_parts = fp.relative_to(root).parts if fp != root else ()
        if any(p in exclude_dirs for p in rel_parts):
            continue
        # Skip directories themselves (only collect files)
        if fp.is_file() and fp.suffix.lower() in extensions:
            files.append(fp)

    return sorted(files) if sort else files
