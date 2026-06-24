#!/usr/bin/env python3
"""CI version consistency check — verifies versions and tool counts match."""
import json
import sys

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("SKIP: tomllib/tomli not available", file=sys.stderr)
        sys.exit(0)

errors = []

# Load version files
try:
    with open("pyproject.toml", "rb") as f:
        ppt = tomllib.load(f)
    pv = ppt["project"]["version"]
except Exception as e:
    errors.append(f"pyproject.toml: {e}")
    pv = None

try:
    with open("manifest.json") as f:
        mf = json.load(f)
    mv = mf["version"]
except Exception as e:
    errors.append(f"manifest.json: {e}")
    mv = None

try:
    with open("tools_config.json") as f:
        tc = json.load(f)
    tv = tc["__meta"]["version"]
    tc_count = len(tc["tools"])
except Exception as e:
    errors.append(f"tools_config.json: {e}")
    tv = None
    tc_count = None

if pv and mv and pv != mv:
    errors.append(f"pyproject.toml ({pv}) != manifest.json ({mv})")
if pv and tv and pv != tv:
    errors.append(f"pyproject.toml ({pv}) != tools_config.json ({tv})")
if tc_count is not None and len(mf.get("tools", [])) != tc_count:
    errors.append(f"tools_config.json ({tc_count} tools) != manifest.json ({len(mf['tools'])} tools)")
if tc_count is not None and tc_count != 60:
    errors.append(f"Expected 60 tools, got {tc_count}")

if errors:
    print("VERSION/CONFIG INCONSISTENCIES:", file=sys.stderr)
    for e in errors:
        print(f"  FAIL: {e}", file=sys.stderr)
    sys.exit(1)

print(f"✅ Version {pv} consistent, {tc_count} tools in sync")
