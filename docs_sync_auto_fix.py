#!/usr/bin/env python3
"""
docs_sync_auto_fix.py — Update README.md automatisch o.b.v. code changes.

Genereert:
  - Tool counts update
  - Tool lijst update
  - Badge update (tests count)
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()


def count_tools() -> int:
    """Count all Python tools in root directory."""
    support_modules = {"__init__.py", "_protect.py", "i18n.py"}
    return sum(1 for fp in ROOT.glob("*.py") if fp.name not in support_modules)


def count_tests() -> int:
    """Count unit tests."""
    test_dir = ROOT / "tests"
    if not test_dir.exists():
        return 0
    count = 0
    for fp in test_dir.glob("*.py"):
        if fp.name.startswith("test_") or fp.name == "__init__.py":
            content = fp.read_text(encoding="utf-8", errors="replace")
            count += content.count("def test_")
    return count


def generate_tool_list() -> str:
    """Generate a formatted tool list for README."""
    tools = []
    for fp in sorted(ROOT.glob("*.py")):
        if fp.name not in {"__init__.py", "_protect.py", "i18n.py"}:
            # Read first docstring line
            content = fp.read_text(encoding="utf-8", errors="replace")
            docs_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
            if docs_match:
                first_line = docs_match.group(1).strip().split("\n")[0]
                desc = first_line.replace(" — ", " — ")[:80]
            else:
                desc = fp.stem.replace("_", " ").title()
            tools.append(f"| `{fp.name}` | {desc} |")
    return "\n".join(tools)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Docs Sync Auto Fix — Update README automatically"
    )
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Toon wat er zou veranderen")
    parser.add_argument("--tool-list", action="store_true",
                        help="Genereer tool lijst voor README")
    parser.add_argument("--count", action="store_true",
                        help="Toon tool + test counts")
    args = parser.parse_args()

    tool_count = count_tools()
    test_count = count_tests()

    if args.count:
        print(f"Tools: {tool_count}")
        print(f"Tests: {test_count}")
        return

    if args.tool_list:
        print(generate_tool_list())
        return

    # Default: show stats
    print()
    print("=" * 60)
    print(" 📚 DOCS SYNC AUTO-FIX")
    print("=" * 60)
    print(f"   Tools on disk:  {tool_count}")
    print(f"   Unit tests:     {test_count}")

    readme = ROOT / "README.md"
    if readme.exists():
        content = readme.read_text(encoding="utf-8")
        # Check current count in README
        tool_match = re.search(r'(\d+)\s+tools', content)
        if tool_match:
            current_count = int(tool_match.group(1))
            if current_count != tool_count:
                print(f"   ⚠️  README says {current_count} tools, disk has {tool_count}")
                if not args.dry_run:
                    new_content = content.replace(
                        f"{current_count} tools",
                        f"{tool_count} tools"
                    )
                    readme.write_text(new_content, encoding="utf-8")
                    print(f"   ✅ README updated: {current_count} → {tool_count} tools")
            else:
                print(f"   ✅ README: {tool_count} tools (up-to-date)")
        else:
            print(f"   ⚠️  Could not find tool count in README")

        test_match = re.search(r'tests[- ](\d+)', content)
        if test_match:
            current_tests = int(test_match.group(1))
            if current_tests != test_count:
                print(f"   ⚠️  README says {current_tests} tests, disk has {test_count}")
        else:
            print(f"   ⚠️  Could not find test count in README")
    else:
        print(f"   ❌ README.md niet gevonden")

    print(f"   Use --tool-list for markdown table")
    print(f"   Use --count for quick stats")


if __name__ == "__main__":
    main()
