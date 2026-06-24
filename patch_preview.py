#!/usr/bin/env python3
"""
patch_preview.py — Show a diff preview of what a patch would do.

Analyzes a file or code snippet and shows what improvements
would be made before applying them. Works with the code-improvement-loop skill.

Features:
  - Preview formatting fixes (line length, trailing whitespace)
  - Preview suggested improvements
  - Show diff output
  - Side-by-side comparison option
  - JSON output for external tools

Gebruik:
    python patch_preview.py <file>                        # Preview fixes
    python patch_preview.py <file> --side-by-side          # Side-by-side diff
    python patch_preview.py <file> --json                  # JSON output
    python patch_preview.py --code "def foo(): pass"       # Preview code snippet
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import difflib
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_LINE_LENGTH = 100


def read_file(filepath: str) -> tuple[list[str] | None, str | None]:
    """Read a file, return (lines, error)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return content.split("\n"), None
    except Exception as e:
        return None, str(e)


def generate_fixes(lines: list[str], max_line: int = MAX_LINE_LENGTH) -> list[str]:
    """Generate fixed version of the file content."""
    fixed = []
    changes = []

    for i, line in enumerate(lines):
        original = line
        modified = line

        # Fix trailing whitespace
        if modified != modified.rstrip():
            modified = modified.rstrip()
            if modified != original:
                changes.append({
                    "line": i + 1,
                    "type": "trailing_whitespace",
                    "original": repr(original),
                    "fixed": repr(modified),
                })

        # Fix long lines (add line continuation for Python)
        if len(modified) > max_line and i < len(lines) - 1:
            # Try to find a good break point
            if any(c in modified for c in [" and ", " or ", ", ", " + ", " | "]):
                changes.append({
                    "line": i + 1,
                    "type": "long_line",
                    "original": f"{len(modified)} chars: {modified[:80]}...",
                    "fixed": f"(zou gebroken moeten worden in meerdere regels)",
                })

        fixed.append(modified)

    # Ensure trailing newline
    if fixed and fixed[-1] != "":
        changes.append({
            "line": len(fixed),
            "type": "missing_newline",
            "original": "Geen newline aan einde",
            "fixed": "Newline toegevoegd",
        })
        fixed.append("")

    return fixed, changes


def generate_all_fixes(lines: list[str], filepath: str,
                       max_line: int = MAX_LINE_LENGTH) -> list[dict]:
    """Generate a comprehensive list of suggested fixes."""
    fixes = []

    # 1. Trailing whitespace
    for i, line in enumerate(lines, 1):
        if line != line.rstrip():
            fixes.append({
                "line": i,
                "type": "trailing_whitespace",
                "severity": "low",
                "description": "Trailing whitespace detected",
                "original": repr(line),
                "fixed": repr(line.rstrip()),
            })

    # 2. Long lines
    for i, line in enumerate(lines, 1):
        if len(line) > max_line:
            fixes.append({
                "line": i,
                "type": "long_line",
                "severity": "medium",
                "description": f"Line too long ({len(line)} > {max_line})",
                "original": line[:100],
                "fixed": "(overweeg op te splitsen)",
            })

    # 3. Missing newline at EOF
    if lines and lines[-1] != "":
        fixes.append({
            "line": len(lines),
            "type": "missing_newline",
            "severity": "low",
            "description": "No newline at end of file",
            "original": "EOF zonder newline",
            "fixed": "Newline toegevoegd",
        })

    # 4. Dead imports (Python)
    ext = Path(filepath).suffix.lower()
    if ext == ".py":
        try:
            import ast
            tree = ast.parse("\n".join(lines), filename=filepath)
            imported = {}
            used = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported[alias.asname or alias.name] = node.lineno
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        imported[alias.asname or alias.name] = node.lineno
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    used.add(node.id)

            for name, line in imported.items():
                root_name = name.split(".")[0]
                if root_name not in used:
                    fixes.append({
                        "line": line,
                        "type": "unused_import",
                        "severity": "medium",
                        "description": f"Unused import: '{name}'",
                        "original": f"import {name}",
                        "fixed": "(verwijderen)",
                    })
        except SyntaxError:
            pass

    # Sort by line number
    fixes.sort(key=lambda x: x["line"])
    return fixes


def generate_diff(lines_before: list[str], lines_after: list[str],
                  filepath: str) -> str:
    """Generate a unified diff string."""
    diff = difflib.unified_diff(
        lines_before,
        lines_after,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
        lineterm="",
    )
    return "\n".join(diff)


def print_side_by_side(lines_before: list[str], lines_after: list[str]) -> None:
    """Print a side-by-side comparison of original vs fixed."""
    max_lines = max(len(lines_before), len(lines_after))
    line_width = 50

    print(f"\n{'='*120}")
    print(f" {'ORIGINEEL'.ljust(line_width)} | {'GEFIXED'.ljust(line_width)}")
    print(f"{'='*120}")

    for i in range(max_lines):
        before = lines_before[i] if i < len(lines_before) else ""
        after = lines_after[i] if i < len(lines_after) else ""

        if before != after:
            prefix = "> "
        else:
            prefix = "  "

        # Truncate long lines
        before_display = before[:line_width - 3]
        after_display = after[:line_width - 3]
        if len(before) > line_width - 3:
            before_display += "..."
        if len(after) > line_width - 3:
            after_display += "..."

        print(f"{prefix}{before_display.ljust(line_width)} | {after_display.ljust(line_width)}")

    print()


def print_report(fixes: list[dict], diff: str, filepath: str,
                 side_by_side: bool = False, lines_before: list = None,
                 lines_after: list = None) -> None:
    """Print a formatted patch preview report."""
    total = len(fixes)
    severity_counts = {}
    for f in fixes:
        sev = f.get("severity", "info")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    print(f"\n{'='*60}")
    print(f" 🔍 PATCH PREVIEW — {filepath}")
    print(f"{'='*60}")
    print(f"   Totaal fixes: {total}")
    print(f"   🔴 High:   {severity_counts.get('high', 0)}")
    print(f"   🟡 Medium: {severity_counts.get('medium', 0)}")
    print(f"   🟢 Low:    {severity_counts.get('low', 0)}")
    print()

    if fixes:
        print(f" ── Voorgestelde Wijzigingen ({total}) ──")
        for fix in fixes:
            severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(fix["severity"], "💡")
            print(f"   {severity_icon} L{fix['line']} | {fix['type']}: {fix['description']}")
            print(f"       ❌ {fix['original'][:80]}")
            print(f"       ✅ {fix['fixed'][:80]}")
        print()

    if side_by_side and lines_before and lines_after:
        print_side_by_side(lines_before, lines_after)
    elif diff:
        print(f" ── Diff ({len(diff.split(chr(10)))} regels) ──")
        diff_lines = diff.split("\n")
        for line in diff_lines[:30]:
            if line.startswith("+"):
                print(f"   \033[32m{line}\033[0m")
            elif line.startswith("-"):
                print(f"   \033[31m{line}\033[0m")
            elif line.startswith("@@"):
                print(f"   \033[36m{line}\033[0m")
            else:
                print(f"   {line}")
        if len(diff_lines) > 30:
            print(f"   ... ({len(diff_lines) - 30} regels verborgen)")
        print()

    if not fixes:
        print(" ✅ Geen verbeteringen nodig — bestand ziet er goed uit!")
        print()


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="patch_preview.py — Preview what a patch would do before applying",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python patch_preview.py script.py                    # Preview fixes
  python patch_preview.py script.py --side-by-side      # Side-by-side diff
  python patch_preview.py script.py --json              # JSON output
  python patch_preview.py --code "def foo(): pass"      # Preview code snippet
        """,
    )
    parser.add_argument("target", nargs="?", help="Bestand om te previewen")
    parser.add_argument("--code", "-c", help="Code snippet direct previewen")
    parser.add_argument("--side-by-side", "-s", action="store_true",
                        help="Toon side-by-side vergelijking")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--max-line", "-m", type=int, default=MAX_LINE_LENGTH,
                        help=f"Max regel lengte (default: {MAX_LINE_LENGTH})")
    parser.add_argument("--version", action="version", version="patch_preview.py v1.0.0")

    args = parser.parse_args()

    if args.code:
        # Preview code snippet
        lines = args.code.split("\n")
        filepath = "<snippet>"
    elif args.target:
        filepath = args.target
        lines, error = read_file(filepath)
        if error:
            print(f" ❌ Fout bij lezen {filepath}: {error}", file=sys.stderr)
            sys.exit(1)
    else:
        print(" ❌ Geef een bestand of --code snippet", file=sys.stderr)
        sys.exit(1)

    # Generate fixes
    fixes = generate_all_fixes(lines, filepath, args.max_line)
    fixed_lines, _ = generate_fixes(lines, args.max_line)

    # Generate unified diff
    diff = generate_diff(lines, fixed_lines, filepath)

    if args.json:
        output = {
            "file": filepath,
            "total_fixes": len(fixes),
            "fixes": fixes,
            "diff": diff,
            "original_lines": len(lines),
            "fixed_lines": len(fixed_lines),
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print_report(fixes, diff, filepath, args.side_by_side, lines, fixed_lines)


if __name__ == "__main__":
    main()
