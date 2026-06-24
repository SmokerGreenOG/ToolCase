#!/usr/bin/env python3
"""
license_checker.py — Check of alle tools de juiste maker attribution hebben.

Checkt:
  - __maker__ = "SmokerGreenOG" in elk .py bestand
  - import _protect aanwezig
  - LICENSE file bestaat
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
EXPECTED_MAKER = "SmokerGreenOG"


def check_file(fp: Path) -> dict:
    """Check file.
    
        Args:
            fp: Description.
    
        Returns:
            Description.
        """
    try:
        content = fp.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"file": str(fp), "error": "Cannot read"}

    has_maker = EXPECTED_MAKER in content
    has_protect = "_protect" in content

    # Check if it's actually a tool (not utility/init)
    is_tool = (
        fp.name.endswith(".py")
        and not fp.name.startswith("_")
        and not fp.name.startswith("test_")
        and fp.name not in ("__init__.py",)
    )

    issues = []
    if is_tool:
        if not has_maker:
            issues.append(f"Missing __maker__ = '{EXPECTED_MAKER}'")
        if not has_protect:
            issues.append("Missing 'import _protect'")

    return {
        "file": fp.name,
        "is_tool": is_tool,
        "has_maker": has_maker,
        "has_protect": has_protect,
        "issues": issues,
        "ok": len(issues) == 0,
    }


def check_all() -> list[dict]:
    """Check all.
        """
    results = []
    for fp in sorted(ROOT.glob("*.py")):
        results.append(check_file(fp))

    # Check LICENSE
    lic = ROOT / "LICENSE"
    if not lic.exists():
        results.append({"file": "LICENSE", "ok": False, "issues": ["LICENSE ontbreekt"]})

    return results


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(description="License Checker")
    parser.add_argument("--json", "-j", action="store_true")
    args = parser.parse_args()

    results = check_all()
    tools = [r for r in results if r.get("is_tool")]
    ok_count = sum(1 for r in tools if r.get("ok"))
    bad_count = sum(1 for r in tools if not r.get("ok"))

    if args.json:
        print(json.dumps({
            "tools_checked": len(tools),
            "ok": ok_count,
            "missing": bad_count,
            "details": [
                {"file": r["file"], "issues": r.get("issues", [])}
                for r in tools if not r.get("ok")
            ]
        }, indent=2))
    else:
        print()
        print("=" * 60)
        print(" 📜 LICENSE CHECKER")
        print("=" * 60)
        print(f"   Tools checked: {len(tools)}")
        print(f"   ✅ OK:          {ok_count}")
        print(f"   ❌ Missing:     {bad_count}")
        print()

        for r in tools:
            if not r.get("ok"):
                for issue in r.get("issues", []):
                    print(f"   ❌ {r['file']}: {issue}")
            else:
                print(f"   ✅ {r['file']}")

        print()
        status = "❌ FAIL" if bad_count > 0 else "✅ ALL OK"
        print(f"   Status: {status}")

    sys.exit(1 if bad_count > 0 else 0)


if __name__ == "__main__":
    main()
