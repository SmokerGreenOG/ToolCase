"""ToolCase shared core — internal package for cross-tool helpers.

Centralizes commonly duplicated functions used across multiple ToolCase tools.
Import from here instead of re-implementing in each tool.

Currently shared:
    normalize_url     — URL normalisation (strip query, trailing slash, collapse //)
    collect_source_files — Recursive file discovery with exclude dirs and extension filter

Safety primitives (safe_run, safe_delete) remain as top-level modules
for zero-dependency import from any single tool.
"""

from toolcase_core.utils import collect_source_files, normalize_url

__all__ = [
    "normalize_url",
    "collect_source_files",
]
