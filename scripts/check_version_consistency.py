#!/usr/bin/env python3
"""CI version consistency check — verifies versions and tool counts match across ALL sources.

Checks: pyproject.toml, manifest.json, tools_config.json, __init__.py (runtime),
improve.py (--version output), README.md badge, CHANGELOG.md heading, SKILL.md.
"""
import json
import re
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("SKIP: tomllib/tomli not available", file=sys.stderr)
        sys.exit(0)

ROOT = Path(__file__).parent.parent
errors = []

# ── Load pyproject.toml version (canonical) ──────────────
try:
    with open(ROOT / "pyproject.toml", "rb") as f:
        ppt = tomllib.load(f)
    canonical = ppt["project"]["version"]
except Exception as e:
    errors.append(f"pyproject.toml: {e}")
    canonical = None

def check_file(path: str, pattern: str, label: str) -> None:
    """Check that a file contains the canonical version."""
    if canonical is None:
        return
    try:
        content = (ROOT / path).read_text(encoding="utf-8")
        m = re.search(pattern, content)
        if not m:
            errors.append(f"{path}: version not found with pattern {pattern!r}")
            return
        found = m.group(1)
        if found != canonical:
            errors.append(f"{path}: {found} != {canonical} ({label})")
    except FileNotFoundError:
        pass  # optional file
    except Exception as e:
        errors.append(f"{path}: {e}")

# ── Core config files ────────────────────────────────────
try:
    with open(ROOT / "manifest.json") as f:
        mf = json.load(f)
    mv = mf["version"]
    if canonical and mv != canonical:
        errors.append(f"manifest.json ({mv}) != pyproject.toml ({canonical})")
except Exception as e:
    errors.append(f"manifest.json: {e}")

try:
    with open(ROOT / "tools_config.json") as f:
        tc = json.load(f)
    tv = tc["__meta"]["version"]
    tc_count = len(tc["tools"])
    if canonical and tv != canonical:
        errors.append(f"tools_config.json ({tv}) != pyproject.toml ({canonical})")
    if tc_count != 60:
        errors.append(f"Expected 60 tools, got {tc_count}")
except Exception as e:
    errors.append(f"tools_config.json: {e}")

# ── Runtime version (__init__.py) ─────────────────────────
check_file(
    "__init__.py",
    r'__version__\s*=\s*"([^"]+)"',
    "__init__.__version__",
)

# ── improve.py --version output ───────────────────────────
check_file(
    "improve.py",
    r'version="improve\.py v([^"]+)"',
    "improve.py --version",
)

# ── improve.py embedded version strings ───────────────────
check_file(
    "improve.py",
    r"VERSION=['\"]([^'\"]+)['\"]",
    "improve.py VERSION=",
)

# ── README badge ─────────────────────────────────────────
check_file(
    "README.md",
    r"version-([\d.]+)-",
    "README.md badge",
)

# ── CHANGELOG heading ─────────────────────────────────────
check_file(
    "CHANGELOG.md",
    r"## \[([\d.]+)\]",
    "CHANGELOG.md heading",
)

# ── SKILL.md ──────────────────────────────────────────────
check_file(
    "SKILL.md",
    r"version:\s*([\d.]+)",
    "SKILL.md version",
)

# ── GITHUB_SETUP.md tag references ────────────────────────
check_file(
    "GITHUB_SETUP.md",
    r"v([\d.]+)",
    "GITHUB_SETUP.md tag",
)

# ── Report ────────────────────────────────────────────────
if errors:
    print("VERSION/CONFIG INCONSISTENCIES:", file=sys.stderr)
    for e in errors:
        print(f"  FAIL: {e}", file=sys.stderr)
    sys.exit(1)

print(f"✅ Version {canonical} consistent across all sources, {tc_count} tools in sync")
