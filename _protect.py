#!/usr/bin/env python3
"""
attribution.py — Central maker constant for ToolCase v5.4.

Exports MAKER = "SmokerGreenOG" for all ToolCase modules to reference.
Every tool imports this module to access the canonical maker name.

HONESTY NOTE: This module does NOT scan importing modules for their
__maker__ attribute. It only verifies its own internal constant via a
hardcoded hash. If you modify __maker__ in another file but leave this
file intact, the import will succeed.

For actual release integrity, use:
  - Signed Git tags (git tag -s)
  - SHA-256 release checksums
  - Sigstore attestations
  - GitHub artifact attestations (built-in for Actions)

This module is the SINGLE SOURCE OF TRUTH for the maker name.
If you need to change the maker, change it HERE, not in individual files.

DO NOT REMOVE THIS FILE. All ToolCase modules depend on it.
"""

import hashlib
import sys

# ── Expected SHA256 hash of "SmokerGreenOG" ────────────
_EXPECTED_HASH = "53b3b002ec207a652daf7d75f6ff0252e3d8d5d2f094eecd9f1220a0dd90da05"

# ── Self-integrity check ───────────────────────────────
_actual_maker = "SmokerGreenOG"
_actual_hash = hashlib.sha256(_actual_maker.encode("utf-8")).hexdigest()

if _actual_hash != _EXPECTED_HASH:
    print(
        f"\n{'=' * 60}",
        f"🔒 TOOLCASE ATTRIBUTION CHECK FAILED",
        f"{'=' * 60}",
        f"",
        f"  The central maker constant has been tampered with.",
        f"  Expected: SmokerGreenOG",
        f"  Found:    {_actual_maker}",
        f"",
        f"  Restore the original value to use ToolCase.",
        f"{'=' * 60}",
        sep="\n",
    )
    sys.exit(1)

# Export the canonical maker name
__all__ = ["MAKER"]
MAKER = _actual_maker
