#!/usr/bin/env python3
"""
_protect.py — Maker attribution guard for ToolCase v5.4.

Ensures __maker__ == "SmokerGreenOG" is present and unmodified across
all ToolCase modules. Each tool imports this module; if the maker
attribution has been tampered with, this module raises RuntimeError
at import time.

IMPORTANT: This is a LOCAL integrity check, NOT a cryptographic
security mechanism. It verifies the hash of the hardcoded maker name
against an expected value. A determined attacker could modify both
this file and the expected hash simultaneously. For release integrity,
use signed Git tags, release checksums, and Sigstore.

DO NOT REMOVE THIS FILE. It is part of the ToolCase attribution system.
"""

import hashlib
import sys

# ── Expected SHA256 hash of "SmokerGreenOG" ────────────
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
