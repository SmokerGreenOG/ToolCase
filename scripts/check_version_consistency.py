#!/usr/bin/env python3
"""CI version consistency check — verifies versions, tool counts, and integrity across ALL sources.

Checks: pyproject.toml (canonical), manifest.json, tools_config.json, __init__.py,
improve.py (--version output), README.md, CHANGELOG.md, SKILL.md, dashboard.html,
SECURITY.md, GITHUB_SETUP.md, i18n.py.

All files are MANDATORY — missing files cause failure.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("SKIP: tomllib/tomli not available", file=sys.stderr)
        sys.exit(0)

ROOT = Path(__file__).parent.parent
errors = []

# ── Canonical version from pyproject.toml ──────────────
try:
    with open(ROOT / "pyproject.toml", "rb") as f:
        ppt = tomllib.load(f)
    canonical = ppt["project"]["version"]
except Exception as e:
    errors.append(f"pyproject.toml: CANNOT READ — {e}")
    canonical = None


def require_file(path: str, label: str) -> str:
    """Read a file; fail if missing."""
    fp = ROOT / path
    if not fp.exists():
        errors.append(f"{path}: MISSING (required for {label})")
        return ""
    return fp.read_text(encoding="utf-8")


def check_version(path: str, label: str, pattern: str, content: str = None) -> None:
    """Check that the file contains EXACTLY the canonical version."""
    if canonical is None:
        return
    if content is None:
        content = require_file(path, label)
        if not content:
            return
    m = re.search(pattern, content)
    if not m:
        errors.append(f"{path}: version not found ({label})")
        return
    found = m.group(1)
    if found != canonical:
        errors.append(f"{path}: {found} != {canonical} ({label})")

# ── Mandatory config files ─────────────────────────────
try:
    with open(ROOT / "manifest.json") as f:
        mf = json.load(f)
    mv = mf["version"]
    if canonical and mv != canonical:
        errors.append(f"manifest.json: {mv} != {canonical}")
except FileNotFoundError:
    errors.append("manifest.json: MISSING (required)")
except Exception as e:
    errors.append(f"manifest.json: {e}")

try:
    with open(ROOT / "tools_config.json") as f:
        tc = json.load(f)
    tv = tc["__meta"]["version"]
    tc_count = len(tc["tools"])
    if canonical and tv != canonical:
        errors.append(f"tools_config.json ({tv}) != pyproject.toml ({canonical})")
    # Tool count must match manifest.json, not a hardcoded number
    try:
        with open(ROOT / "manifest.json") as mf:
            mf_data = json.load(mf)
        mf_count = len(mf_data.get("tools", []))
        if tc_count != mf_count:
            errors.append(f"tools_config.json ({tc_count} tools) != manifest.json ({mf_count} tools)")
    except Exception:
        pass  # manifest check is done separately below
except FileNotFoundError:
    errors.append("tools_config.json: MISSING (required)")
except Exception as e:
    errors.append(f"tools_config.json: {e}")

# ── Runtime version ────────────────────────────────────
check_version("__init__.py", "__init__.__version__", r'__version__\s*=\s*"([^"]+)"')
check_version("improve.py", "improve.py --version", r'version="improve\.py v([^"]+)"')

# ── Actual CLI output ──────────────────────────────────
if canonical:
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "improve.py"), "--version"],
            capture_output=True, text=True, timeout=10,
        )
        cli_out = result.stdout.strip()
        cli_expected = f"improve.py v{canonical}"
        if cli_out != cli_expected:
            errors.append(f"CLI --version: '{cli_out}' != '{cli_expected}'")
        if result.returncode != 0:
            errors.append(f"CLI --version: exit code {result.returncode}")
    except Exception as e:
        errors.append(f"CLI --version: {e}")

# ── Documentation files ────────────────────────────────
check_version("README.md", "README badge", r"version-([\d.]+)-")
check_version("CHANGELOG.md", "CHANGELOG heading", r"## \[([\d.]+)\]")
check_version("SKILL.md", "SKILL version", r"version:\s*([\d.]+)")
check_version("GITHUB_SETUP.md", "GITHUB_SETUP tag", r"v([\d.]+)")

# ── dashboard.html ─────────────────────────────────────
dashboard = require_file("dashboard.html", "dashboard version")
if dashboard:
    check_version("dashboard.html", "dashboard <title>", r"ToolCase v([\d.]+)", dashboard)
    # Also check <span id="version">
    m2 = re.search(r'id="version">v([\d.]+)<', dashboard)
    if m2 and m2.group(1) != canonical:
        errors.append(f"dashboard.html span: {m2.group(1)} != {canonical}")

# ── SECURITY.md ────────────────────────────────────────
security = require_file("SECURITY.md", "security policy")
if security:
    m = re.search(r'\|\s*([\d.]+)\.x\s*\|', security)
    if m and not canonical.startswith(m.group(1)):
        errors.append(f"SECURITY.md: supports {m.group(1)}.x != {canonical}")

# ── icon.svg ──────────────────────────────────────────
icon_svg = require_file("icon.svg", "icon")
if icon_svg:
    m = re.search(r">v(\d+\.\d+\.\d+)<", icon_svg)
    if m and m.group(1) != canonical:
        errors.append(f"icon.svg: v{m.group(1)} != v{canonical}")

# ── tests/__init__.py ──────────────────────────────────
test_init = require_file("tests/__init__.py", "test suite init")
if test_init:
    m = re.search(r"ToolCase v(\d+\.\d+\.\d+)", test_init)
    if m and m.group(1) != canonical:
        errors.append(f"tests/__init__.py: v{m.group(1)} != v{canonical}")

# ── i18n.py ────────────────────────────────────────────
i18n = require_file("i18n.py", "i18n translations")
if i18n:
    # Check version in header
    m = re.search(r"v(\d+\.\d+\.\d+)", i18n)
    if m and m.group(1) != canonical:
        errors.append(f"i18n.py header: v{m.group(1)} != v{canonical}")
    # Check old skill names are gone
    if "code-improvement-loop" in i18n:
        errors.append("i18n.py: contains old skill name 'code-improvement-loop'")
    # Check old tool counts
    if "34 tools" in i18n or "34 Werkzeuge" in i18n:
        errors.append("i18n.py: contains old tool count '34'")

# ── Manifest/tools_config cross-check ──────────────────
try:
    with open(ROOT / "manifest.json", encoding="utf-8") as f:
        mf = json.load(f)
    with open(ROOT / "tools_config.json", encoding="utf-8") as f:
        tc = json.load(f)

    # Extract script names from manifest (list of dicts with "script" key)
    manifest_scripts = {t.get("script", "") for t in mf.get("tools", []) if isinstance(t, dict)}
    # Extract script names from tools_config (list of dicts with "name" key)
    config_scripts = {t.get("name", "") for t in tc.get("tools", []) if isinstance(t, dict)}

    # Cross-check
    only_manifest = manifest_scripts - config_scripts
    only_config = config_scripts - manifest_scripts
    if only_manifest:
        errors.append(f"Tools in manifest not in config: {sorted(only_manifest)}")
    if only_config:
        errors.append(f"Tools in config not in manifest: {sorted(only_config)}")

    # Check tool IDs match
    manifest_ids = {t.get("id") for t in mf.get("tools", []) if isinstance(t, dict)}
    config_ids = {t.get("id") for t in tc.get("tools", []) if isinstance(t, dict)}
    only_mf_ids = manifest_ids - config_ids
    only_cf_ids = config_ids - manifest_ids
    if only_mf_ids:
        errors.append(f"Tool IDs in manifest not in config: {sorted(only_mf_ids)}")
    if only_cf_ids:
        errors.append(f"Tool IDs in config not in manifest: {sorted(only_cf_ids)}")
except json.JSONDecodeError as e:
    errors.append(f"Cross-check JSON error: {e}")
except FileNotFoundError as e:
    errors.append(f"Cross-check file missing: {e}")
except Exception as e:
    errors.append(f"Cross-check error: {type(e).__name__}: {e}")

# ── Report ─────────────────────────────────────────────
if errors:
    print(f"VERSION/CONFIG INCONSISTENCIES ({len(errors)}):", file=sys.stderr)
    for e in errors:
        print(f"  FAIL: {e}", file=sys.stderr)
    sys.exit(1)

tc_count = tc_count if 'tc_count' in dir() else "?"
print(f"✅ Version {canonical} consistent across all sources, {tc_count} tools in sync")
