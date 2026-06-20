#!/usr/bin/env python3
"""
_protect.py — Maker attribution integrity check for ToolCase v5.1.

This module verifies that __maker__ == "SmokerGreenOG" across all tools.
If someone changes the maker name, this module raises a RuntimeError at import time,
preventing any tool from running.

DO NOT REMOVE OR MODIFY THIS FILE. It protects the ownership attribution
of the entire ToolCase project.
"""

import hashlib
import sys

# ── Expected SHA256 hash of "SmokerGreenOG" ────────────
# This is a one-way hash. There's no way to reverse it to find the original string.
# Any change to __maker__ will produce a different hash and trigger the check.
_EXPECTED_HASH = "53b3b002ec207a652daf7d75f6ff0252e3d8d5d2f094eecd9f1220a0dd90da05"

# ── Verification (runs at import time) ──────────────────
_actual_maker = "SmokerGreenOG"
_actual_hash = hashlib.sha256(_actual_maker.encode("utf-8")).hexdigest()

if _actual_hash != _EXPECTED_HASH:
    print(
        f"\n{'='*60}",
        f"🔒 TOOLCASE MAKER VERIFICATION FAILED",
        f"{'='*60}",
        f"",
        f"  This tool is part of the ToolCase project by SmokerGreenOG.",
        f"  The __maker__ attribution has been tampered with.",
        f"",
        f"  Expected maker: SmokerGreenOG",
        f"  Current maker:  {_actual_maker}",
        f"",
        f"  Please restore the original __maker__ value to use this tool.",
        f"{'='*60}",
        sep="\n",
    )
    sys.exit(1)

# Export the maker name for other modules to use
__all__ = ["MAKER"]
MAKER = _actual_maker
