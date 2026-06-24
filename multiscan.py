#!/usr/bin/env python3
"""
multiscan.py — Multi-taal code quality scanner.

Scant project directories op code quality issues in Python, TypeScript/TSX,
en Rust bestanden. Per taal specifieke checks.

Gebruik:
    python multiscan.py <path>                       # Scan alles
    python multiscan.py <path> --lang ts,rs,py       # Specifieke talen
    python multiscan.py <path> --limit 100            # Max regel lengte
    python multiscan.py <path> --json                 # JSON output
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────────────────────────────
# Globals & constants
# ──────────────────────────────────────────────────────────────────────

DEFAULT_MAX_LINE_LENGTH = 100

EXCLUDE_DIRS = {
    "node_modules",
    "target",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".eggs",
    "build",
    "dist",
    ".next",
}

LANG_CONFIG = {
    "py": {"patterns": ["*.py"], "check_fn": "check_python"},
    "ts": {"patterns": ["*.ts"], "check_fn": "check_ts"},
    "tsx": {"patterns": ["*.tsx"], "check_fn": "check_ts"},
    "rs": {"patterns": ["*.rs"], "check_fn": "check_rust"},
}

LANG_ALIASES = {
    "typescript": "ts",
    "python": "py",
    "rust": "rs",
}

# ──────────────────────────────────────────────────────────────────────
# Per-language check functions
# ──────────────────────────────────────────────────────────────────────


def check_python(filepath: Path, max_line: int) -> tuple:
    """Check Python file: AST syntax + line length + trailing whitespace."""
    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return (str(filepath), "py", [f"Error reading file: {e}"], False, 0, 0)

    # Syntax check via ast.parse
    syntax_ok = True
    try:
        ast.parse(source, filename=str(filepath))
    except SyntaxError as e:
        syntax_ok = False
        syntax_issues = [f"SyntaxError: {e}"]
    except Exception as e:
        syntax_ok = False
        syntax_issues = [f"Parse error: {e}"]

    lines = source.split("\n")
    line_count = len(lines)
    long_lines = 0
    issues = []

    if not syntax_ok:
        issues.extend(syntax_issues)

    for i, line in enumerate(lines, 1):
        stripped = line.rstrip("\r")

        # Line length
        if len(stripped) > max_line:
            long_lines += 1
            issues.append(f"  {i:4d} | E501: Line too long ({len(stripped)} > {max_line})")

        # Trailing whitespace
        if stripped != stripped.rstrip():
            issues.append(f"  {i:4d} | W291: Trailing whitespace")

    # EOF newline
    if lines and lines[-1] != "":
        issues.append(f"  {line_count:4d} | W292: No newline at end of file")

    return (str(filepath), "py", issues, syntax_ok, line_count, long_lines)


def check_ts(filepath: Path, max_line: int) -> tuple:
    """Check TypeScript/TSX file: line length, trailing whitespace, TODO/FIXME, long imports."""
    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return (str(filepath), "ts", [f"Error reading file: {e}"], False, 0, 0)

    lines = source.split("\n")
    line_count = len(lines)
    long_lines = 0
    issues = []
    syntax_ok = True  # No AST check for TS

    for i, line in enumerate(lines, 1):
        stripped = line.rstrip("\r")

        # Line length
        if len(stripped) > max_line:
            long_lines += 1
            issues.append(f"  {i:4d} | Line too long ({len(stripped)} > {max_line})")

        # Trailing whitespace
        if stripped != stripped.rstrip():
            issues.append(f"  {i:4d} | Trailing whitespace")

        # Check for markers in comments
        comment_match = re.search(r"(//|/\*|#).*?(TODO|FIXME|HACK|XXX)", stripped)
        if comment_match:
            issues.append(f"  {i:4d} | NOTE: Contains '{comment_match.group(2)}'")

        # Long import lines
        if re.match(r"^\s*(import|export)\s", stripped) and len(stripped) > max_line:
            issues.append(f"  {i:4d} | Long import/export ({len(stripped)} chars)")

    # EOF newline
    if lines and lines[-1] != "":
        issues.append(f"  {line_count:4d} | W292: No newline at end of file")

    lang = "tsx" if filepath.suffix == ".tsx" else "ts"
    return (str(filepath), lang, issues, syntax_ok, line_count, long_lines)


def check_rust(filepath: Path, max_line: int) -> tuple:
    """Check Rust file: line length, trailing whitespace, unsafe/unwrap, TODO/FIXME."""
    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return (str(filepath), "rs", [f"Error reading file: {e}"], False, 0, 0)

    lines = source.split("\n")
    line_count = len(lines)
    long_lines = 0
    issues = []
    syntax_ok = True  # No AST check for Rust
    unsafe_count = 0
    unwrap_count = 0

    for i, line in enumerate(lines, 1):
        stripped = line.rstrip("\r")

        # Line length
        if len(stripped) > max_line:
            long_lines += 1
            issues.append(f"  {i:4d} | Line too long ({len(stripped)} > {max_line})")

        # Trailing whitespace
        if stripped != stripped.rstrip():
            issues.append(f"  {i:4d} | Trailing whitespace")

        # Check for markers in comments
        comment_match = re.search(r"(//|/\*|#).*?(TODO|FIXME|HACK|XXX)", stripped)
        if comment_match:
            issues.append(f"  {i:4d} | NOTE: Contains '{comment_match.group(2)}'")

        # Count unsafe blocks (non-comment)
        if "unsafe" in stripped and not stripped.strip().startswith("//"):
            unsafe_count += stripped.count("unsafe")

        # Count .unwrap() calls (non-comment)
        if ".unwrap()" in stripped and not stripped.strip().startswith("//"):
            unwrap_count += stripped.count(".unwrap()")

    # Summary issues for Rust-specific metrics
    if unsafe_count > 0:
        issues.append(f"  ─    | WARN: {unsafe_count} 'unsafe' usage(s) found")
    if unwrap_count > 0:
        issues.append(f"  ─    | WARN: {unwrap_count} '.unwrap()' call(s) found")

    # EOF newline
    if lines and lines[-1] != "":
        issues.append(f"  {line_count:4d} | W292: No newline at end of file")

    return (str(filepath), "rs", issues, syntax_ok, line_count, long_lines)


# ──────────────────────────────────────────────────────────────────────
# File discovery
# ──────────────────────────────────────────────────────────────────────


def discover_files(root: Path, languages: set[str]) -> list[Path]:
    """Discover all matching source files, excluding known generated dirs."""
    files = []
    patterns = []
    for lang in languages:
        cfg = LANG_CONFIG.get(lang)
        if cfg:
            patterns.extend(cfg["patterns"])

    if not patterns:
        return files

    for pattern in patterns:
        for f in root.rglob(pattern):
            # Skip excluded directories
            parts = f.relative_to(root).parts
            if any(part in EXCLUDE_DIRS for part in parts):
                continue
            files.append(f)

    return sorted(set(files))


# ──────────────────────────────────────────────────────────────────────
# Printing & reporting
# ──────────────────────────────────────────────────────────────────────


def print_report(results: list[tuple], max_line: int) -> None:
    """Print formatted per-file report plus summary."""
    per_lang = defaultdict(list)
    total_files = 0
    total_issues = 0
    total_long = 0

    for (filepath, lang, issues, syntax_ok, line_count, long_lines) in results:
        per_lang[lang].append((filepath, issues, syntax_ok, line_count, long_lines))
        total_files += 1
        total_issues += len(issues)
        total_long += long_lines

        # Per-file report
        status = "✅" if (syntax_ok and not issues) else "⚠"
        print(f"\n{'='*60}")
        print(f" {status} {filepath}")
        print(f"{'='*60}")
        print(f"   Lines: {line_count}  |  Lang: {lang.upper()}  |  Long lines: {long_lines}")
        print(f"   Syntax: {'OK' if syntax_ok else '❌ ERROR'}  |  Issues: {len(issues)}")
        if issues:
            print(f"\n   Issues ({len(issues)}):")
            for issue in issues:
                print(f"    {issue}")
        else:
            print(f"   ✨ Geen issues gevonden")

    # Summary per language
    print(f"\n{'='*60}")
    print(f" 📊 SAMENVATTING")
    print(f"{'='*60}")
    print(f"   Totaal bestanden: {total_files}")
    print(f"   Totaal issues:    {total_issues}")
    print(f"   Totaal lange regels (> {max_line}): {total_long}")
    print()

    for lang in sorted(per_lang.keys()):
        lang_files = per_lang[lang]
        lang_issues = sum(len(i) for _, i, _, _, _ in lang_files)
        lang_ok = sum(1 for _, _, ok, _, _ in lang_files if ok)
        lang_total = len(lang_files)
        print(f"   [{lang.upper()}] {lang_total} bestanden, {lang_ok} syntax OK, {lang_issues} issues")

    print()


def print_json(results: list[tuple], max_line: int) -> None:
    """Output results as JSON."""
    output = {
        "max_line_length": max_line,
        "summary": {
            "total_files": len(results),
            "total_issues": sum(r[2].__len__() for r in results),
            "total_long_lines": sum(r[5] for r in results),
        },
        "per_language": {},
        "files": [],
    }

    for (filepath, lang, issues, syntax_ok, line_count, long_lines) in results:
        output["files"].append({
            "file": filepath,
            "lang": lang,
            "issues": issues,
            "syntax_ok": syntax_ok,
            "line_count": line_count,
            "long_lines": long_lines,
        })
        if lang not in output["per_language"]:
            output["per_language"][lang] = {"files": 0, "issues": 0, "syntax_ok": 0}
        output["per_language"][lang]["files"] += 1
        output["per_language"][lang]["issues"] += len(issues)
        if syntax_ok:
            output["per_language"][lang]["syntax_ok"] += 1

    print(json.dumps(output, indent=2, ensure_ascii=False))


# ──────────────────────────────────────────────────────────────────────
# Main CLI
# ──────────────────────────────────────────────────────────────────────


def resolve_languages(lang_arg: Optional[str]) -> set[str]:
    """Parse --lang argument into normalized language set."""
    if not lang_arg:
        return set(LANG_CONFIG.keys())

    langs = set()
    for part in lang_arg.split(","):
        part = part.strip().lower()
        # Resolve aliases
        if part in LANG_ALIASES:
            part = LANG_ALIASES[part]
        if part in LANG_CONFIG:
            langs.add(part)
        else:
            print(f" ⚠  Onbekende taal: '{part}' — negeer (beschikbaar: py, ts, tsx, rs)", file=sys.stderr)
    return langs


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="multiscan.py — Multi-taal code quality scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Voorbeelden:
  python multiscan.py src/                                   # Scan alles
  python multiscan.py src/ --lang py,rs                      # Alleen Python + Rust
  python multiscan.py src/ --lang ts --limit 120             # TS met max 120 chars
  python multiscan.py src/ --json                            # JSON output
  python multiscan.py src/ --lang ts,rs,py --limit 80        # Max 80 chars
        """,
    )
    parser.add_argument("path", help="Bestand of directory om te scannen")
    parser.add_argument("--lang", "-l",
                        help="Filters op taal (comma-separated: py,ts,tsx,rs)")
    parser.add_argument("--limit", "-m", type=int, default=DEFAULT_MAX_LINE_LENGTH,
                        help=f"Maximum regel lengte (default: {DEFAULT_MAX_LINE_LENGTH})")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output als JSON")
    parser.add_argument("--version", action="version", version="multiscan.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f" ❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    languages = resolve_languages(args.lang)
    if not languages:
        print(" ❌ Geen geldige talen om te scannen", file=sys.stderr)
        sys.exit(1)

    lang_label = ", ".join(sorted(languages))
    print(f"\n🔍 Multiscan v1.0.0 — scanning: {target}")
    print(f"   Talen: {lang_label.upper()}")
    print(f"   Max regel lengte: {args.limit}")
    print(f"{'='*60}")

    if target.is_file():
        # Single file — detect language from extension
        ext = target.suffix.lstrip(".").lower()
        if ext == "tsx":
            ext = "tsx"
        elif ext not in LANG_CONFIG:
            print(f" ❌ Onbekende extensie: .{ext}", file=sys.stderr)
            sys.exit(1)
        if ext not in languages:
            print(f" ⚠  .{ext} niet in geselecteerde talen ({lang_label})", file=sys.stderr)
            sys.exit(1)

        check_fn_name = LANG_CONFIG[ext]["check_fn"]
        check_fn = globals()[check_fn_name]
        results = [check_fn(target, args.limit)]

    else:
        # Directory — discover files
        files = discover_files(target, languages)
        if not files:
            print(f" Geen bestanden gevonden in {target}")
            sys.exit(0)

        print(f" 📁 {len(files)} bestand(en) gevonden")
        results = []
        for f in files:
            ext = f.suffix.lstrip(".").lower()
            if ext == "tsx":
                lang_key = "tsx"
            else:
                lang_key = ext
            check_fn_name = LANG_CONFIG[lang_key]["check_fn"]
            check_fn = globals()[check_fn_name]
            results.append(check_fn(f, args.limit))

    # Output
    if args.json:
        print_json(results, args.limit)
    else:
        print_report(results, args.limit)


if __name__ == "__main__":
    main()
