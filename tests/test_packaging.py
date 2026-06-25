"""Packaging integrity tests — validate pyproject.toml modules exist on disk.

These tests ensure the package configuration stays in sync with the filesystem.
No wheel build required — validates the source tree directly.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_all_py_modules_exist():
    """Every module listed in pyproject.toml py-modules must exist on disk."""
    with open(ROOT / "pyproject.toml", "rb") as f:
        cfg = tomllib.load(f)

    py_modules = cfg["tool"]["setuptools"]["py-modules"]
    missing = [m for m in py_modules if not (ROOT / f"{m}.py").exists()]

    assert not missing, f"py-modules missing from disk: {missing}"


def test_toolcase_core_package_exists():
    """toolcase_core package must be importable."""
    tc = ROOT / "toolcase_core"
    assert tc.is_dir(), "toolcase_core/ directory missing"
    assert (tc / "__init__.py").exists(), "toolcase_core/__init__.py missing"
    assert (tc / "utils.py").exists(), "toolcase_core/utils.py missing"


def test_safe_delete_in_py_modules():
    """safe_delete must be listed in py-modules for wheel inclusion."""
    with open(ROOT / "pyproject.toml", "rb") as f:
        cfg = tomllib.load(f)

    py_modules = cfg["tool"]["setuptools"]["py-modules"]
    assert "safe_delete" in py_modules, "safe_delete missing from py-modules"


def test_safe_run_in_py_modules():
    """safe_run must be listed in py-modules."""
    with open(ROOT / "pyproject.toml", "rb") as f:
        cfg = tomllib.load(f)

    py_modules = cfg["tool"]["setuptools"]["py-modules"]
    assert "safe_run" in py_modules, "safe_run missing from py-modules"


def test_core_helpers_importable():
    """Core helper modules must be importable from source tree."""
    import safe_delete  # noqa: F401
    import safe_run  # noqa: F401
    import toolcase_core  # noqa: F401
    import backup_manager  # noqa: F401
    import release_packager  # noqa: F401


def test_console_scripts_defined():
    """All documented console_scripts must be in pyproject.toml."""
    with open(ROOT / "pyproject.toml", "rb") as f:
        cfg = tomllib.load(f)

    scripts = cfg["project"]["scripts"]
    expected = [
        "toolcase",
        "toolcase-security",
        "toolcase-safe-run",
        "toolcase-rsi",
        "toolcase-doctor",
        "toolcase-release",
    ]
    for name in expected:
        assert name in scripts, f"console_script '{name}' missing from pyproject.toml"


def test_tool_count_matches_registry():
    """manifest.json tool count must match tools_config.json."""
    import json

    manifest = json.loads((ROOT / "manifest.json").read_text())
    config = json.loads((ROOT / "tools_config.json").read_text())

    mf_tools = manifest.get("tools", [])
    cf_tools = config.get("tools", [])

    assert len(mf_tools) == 62, f"manifest.json has {len(mf_tools)} tools, expected 62"
    assert len(cf_tools) == 62, f"tools_config.json has {len(cf_tools)} tools, expected 62"
