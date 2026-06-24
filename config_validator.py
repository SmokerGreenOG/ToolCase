#!/usr/bin/env python3
"""
config_validator.py — Validateert ToolCase config bestanden.

Checkt:
  - tools_config.json vs manifest.json consistentie
  - Alle scripts in config bestaan op disk
  - Category ↔ tool mappings kloppen
  - Verplichte velden per tool
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()


def validate() -> dict:
    """Run all validation checks. Returns report dict."""
    errors = []
    warnings = []
    ok = []

    cfg_path = ROOT / "tools_config.json"
    mf_path = ROOT / "manifest.json"

    # Check files exist
    if not cfg_path.exists():
        errors.append("tools_config.json ontbreekt")
        return {"errors": errors, "warnings": warnings, "ok": ok}
    if not mf_path.exists():
        errors.append("manifest.json ontbreekt")
        return {"errors": errors, "warnings": warnings, "ok": ok}

    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        mf = json.loads(mf_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"JSON parse error: {e}")
        return {"errors": errors, "warnings": warnings, "ok": ok}

    # --- Tool counts ---
    cfg_tools = [t["name"] for t in cfg.get("tools", [])]
    mf_tools = [t["script"] for t in mf.get("tools", [])]
    ok.append(f"tools_config.json: {len(cfg_tools)} tools")
    ok.append(f"manifest.json: {len(mf_tools)} tools")

    if len(cfg_tools) != len(mf_tools):
        errors.append(
            f"Tool count mismatch: cfg={len(cfg_tools)}, manifest={len(mf_tools)}"
        )
    else:
        ok.append("Tool counts: MATCH ✅")

    # --- Missing tools ---
    cfg_set = set(cfg_tools)
    mf_set = set(mf_tools)
    in_mf_not_cfg = mf_set - cfg_set
    in_cfg_not_mf = cfg_set - mf_set

    if in_mf_not_cfg:
        errors.append("In manifest, niet in tools_config: " + ", ".join(sorted(in_mf_not_cfg)))
    if in_cfg_not_mf:
        errors.append("In tools_config, niet in manifest: " + ", ".join(sorted(in_cfg_not_mf)))
    if not in_mf_not_cfg and not in_cfg_not_mf:
        ok.append("All tools in both configs ✅")

    # --- Tools exist on disk ---
    missing_files = []
    for tool in cfg_set | mf_set:
        if not (ROOT / tool).exists():
            missing_files.append(tool)
    if missing_files:
        errors.append("Scripts missing: " + ", ".join(sorted(missing_files)))
    else:
        ok.append(f"All {len(cfg_set | mf_set)} config tools exist on disk ✅")

    # --- Tools on disk NOT in config ---
    support_modules = {"__init__.py", "_protect.py", "i18n.py"}
    all_py = {p.name for p in ROOT.glob("*.py") if p.name not in support_modules}
    config_tools_set = cfg_set | mf_set
    unregistered = all_py - config_tools_set
    if unregistered:
        warnings.append(
            f"Tools on disk NOT in config: {', '.join(sorted(unregistered))}"
        )
    else:
        ok.append("All .py tools registered in config ✅")

    # --- Category mappings ---
    cat_tools = set()
    for cat in cfg.get("categories", []):
        for t in cat.get("tools", []):
            cat_tools.add(t)
    uncategorized = cfg_set - cat_tools
    if uncategorized:
        warnings.append("Uncategorized tools: " + ", ".join(sorted(uncategorized)))
    else:
        ok.append(f"{len(cfg.get('categories', []))} categories cover all tools ✅")

    # --- Required fields per tool ---
    required = ["id", "name", "type", "risk", "tags", "description", "command"]
    for tool in cfg.get("tools", []):
        missing = [f for f in required if f not in tool]
        if missing:
            warnings.append(
                f"{tool.get('name', '?')}: missing fields {missing}"
            )

    return {"errors": errors, "warnings": warnings, "ok": ok}


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="Config Validator — Controleer ToolCase config files"
    )
    parser.add_argument("target", nargs="?", default=None,
                        help="Optional target path (default: ToolCase project root)")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    report = validate()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print()
        print("=" * 50)
        print(" 📋 CONFIG VALIDATOR")
        print("=" * 50)

        has_errors = bool(report["errors"])
        has_warnings = bool(report["warnings"])

        for line in report["ok"]:
            print(f"   ✅ {line}")
        for line in report["warnings"]:
            print(f"   ⚠️  {line}")
        for line in report["errors"]:
            print(f"   ❌ {line}")

        status = "❌ FAIL" if has_errors else "⚠️  WARN" if has_warnings else "✅ ALL OK"
        print()
        print(f"   Status: {status}")
        print()

    sys.exit(1 if report["errors"] else 0)


if __name__ == "__main__":
    main()
