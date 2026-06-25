#!/usr/bin/env python3
"""Check that all modules listed in pyproject.toml exist on disk.

Verifies packaging integrity without requiring a wheel build.
Use: python scripts/check_packaging.py
Exit: 0 = all OK, 1 = missing modules.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    with open(ROOT / "pyproject.toml", "rb") as f:
        cfg = tomllib.load(f)

    py_modules = cfg.get("tool", {}).get("setuptools", {}).get("py-modules", [])
    errors = 0

    for mod in py_modules:
        fpath = ROOT / f"{mod}.py"
        if not fpath.exists():
            print(f"MISSING: {mod}.py (listed in pyproject.toml but not on disk)")
            errors += 1

    # Check toolcase_core package
    tc_init = ROOT / "toolcase_core" / "__init__.py"
    if not tc_init.exists():
        print("MISSING: toolcase_core/__init__.py")
        errors += 1
    tc_utils = ROOT / "toolcase_core" / "utils.py"
    if not tc_utils.exists():
        print("MISSING: toolcase_core/utils.py")
        errors += 1

    # Check extra modules not in py-modules
    extra = ["safe_delete"]
    for mod in extra:
        if mod not in py_modules:
            print(f"MISSING from py-modules: {mod}")
            errors += 1

    if errors:
        print(f"\n{errors} packaging error(s) found")
        return 1

    print(f"Packaging OK: {len(py_modules)} py-modules + toolcase_core all present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
