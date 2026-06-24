#!/usr/bin/env python3
"""
php_complexity.py — PHP cyclomatic complexity & cognitive load analyzer.

Analyseert PHP-bestanden op:
  - Cyclomatische complexiteit (McCabe) per functie/methode
  - Cognitieve load (geneste structures, boolean operatoren tellen zwaarder)
  - Top 5 meest complexe functies, gemiddelden, bestandsstatistieken

Gebruik:
    python php_complexity.py <file.php>
    python php_complexity.py <directory> --recursive
    python php_complexity.py <path> --threshold 10 --json
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════

EXCLUDE_DIRS = {
    "node_modules", "vendor", ".git", "__pycache__", "tests/fixtures",
    ".venv", "venv", "dist", "build", ".cache",
    "storage", "bootstrap/cache", "wp-content/cache",
}

DEFAULT_THRESHOLD = 10  # McCabe warning threshold

# ── PHP function/method detection ──
FUNCTION_START = re.compile(
    r'^\s*(?:(?:public|private|protected|static|abstract|final)\s+)*'
    r'function\s+(\w+)\s*\(',
    re.MULTILINE,
)

# Anonymous function / closure
CLOSURE_START = re.compile(
    r'\bfunction\s*\([^)]*\)\s*(?:\s*use\s*\([^)]*\))?\s*\{',
)

# ── Decision points (each +1 McCabe) ──
DECISION_PATTERNS = [
    re.compile(r'\bif\s*[\(:]'),          # if
    re.compile(r'\belseif\s*[\(:]'),      # elseif
    re.compile(r'\belse\b'),              # else (structural)
    re.compile(r'\bfor\s*\('),            # for
    re.compile(r'\bforeach\s*\('),        # foreach
    re.compile(r'\bwhile\s*\('),          # while
    re.compile(r'\bdo\s*\{'),             # do...while
    re.compile(r'\bswitch\s*\('),         # switch (counts as 1)
    re.compile(r'\bcase\s+'),             # each case (+1)
    re.compile(r'\bcatch\s*\('),          # catch
    re.compile(r'\?\s*(?!>)'),             # ternary operator
    re.compile(r'&&'),                    # logical AND
    re.compile(r'\|\|'),                  # logical OR
    re.compile(r'\band\b'),               # low-precedence AND
    re.compile(r'\bor\b'),                 # low-precedence OR
    re.compile(r'\bxor\b'),               # XOR
]

# ── Nesting incrementors (cognitive load) ──
NESTING_PATTERNS = [
    re.compile(r'\bif\s*[\(:]'),
    re.compile(r'\belseif\s*[\(:]'),
    re.compile(r'\bfor\s*\('),
    re.compile(r'\bforeach\s*\('),
    re.compile(r'\bwhile\s*\('),
    re.compile(r'\bswitch\s*\('),
    re.compile(r'\btry\s*\{'),
    re.compile(r'\bfunction\s*\([^)]*\)\s*\{'),  # closures add nesting
]

# ── Boolean operators (cognitive load weight: 0.5 each) ──
BOOLEAN_PATTERNS = [
    re.compile(r'&&'),
    re.compile(r'\|\|'),
    re.compile(r'\band\b'),
    re.compile(r'\bor\b'),
    re.compile(r'\bxor\b'),
]


# ═══════════════════════════════════════════════════════════════════
# Core analysis
# ═══════════════════════════════════════════════════════════════════


def extract_functions(source: str) -> list[dict]:
    """Extract all function/method bodies from PHP source."""
    functions = []
    # Find named functions/methods
    for match in FUNCTION_START.finditer(source):
        name = match.group(1)
        start = match.end()  # after the opening (

        # Find the matching { by counting braces
        depth = 0
        body_start = -1
        body_end = -1
        for i, c in enumerate(source[start:], start):
            if c == '{':
                if depth == 0:
                    body_start = i + 1
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    body_end = i
                    break

        if body_start >= 0 and body_end >= 0:
            body = source[body_start:body_end]
            functions.append({
                "name": name,
                "line": source[:match.start()].count('\n') + 1,
                "body": body,
                "type": "function",
            })

    return functions


def compute_mccabe(body: str) -> int:
    """Compute McCabe cyclomatic complexity: 1 + sum(decision points)."""
    complexity = 1  # base
    for pattern in DECISION_PATTERNS:
        complexity += len(pattern.findall(body))
    return complexity


def compute_cognitive(body: str) -> float:
    """Compute cognitive load score: nesting depth + boolean weight."""
    score = 0.0
    lines = body.split('\n')
    nesting_depth = 0

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('//') or stripped.startswith('#'):
            continue

        # Track nesting for cognitive load
        opens = sum(1 for p in NESTING_PATTERNS if p.search(stripped))
        closes = stripped.count('}')

        if opens > 0:
            nesting_depth += opens

        if closes > 0:
            nesting_depth = max(0, nesting_depth - closes)

        # Add nesting penalty
        score += nesting_depth * 0.25

        # Add boolean penalty
        for bp in BOOLEAN_PATTERNS:
            score += len(bp.findall(stripped)) * 0.5

    return round(score, 1)


def analyze_php_file(filepath: Path, threshold: int) -> dict:
    """Analyze a single PHP file for complexity."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"file": str(filepath), "error": f"Cannot read: {e}", "functions": []}

    line_count = source.count('\n')
    functions = extract_functions(source)

    results = []
    for func in functions:
        mccabe = compute_mccabe(func["body"])
        cognitive = compute_cognitive(func["body"])
        status = "OK" if mccabe <= threshold else "WARN"

        results.append({
            "name": func["name"],
            "line": func["line"],
            "type": func["type"],
            "mccabe": mccabe,
            "cognitive": cognitive,
            "status": status,
        })

    # Top 5 most complex
    by_mccabe = sorted(results, key=lambda f: f["mccabe"], reverse=True)[:5]
    avg_mccabe = round(sum(f["mccabe"] for f in results) / max(len(results), 1), 1)
    avg_cognitive = round(sum(f["cognitive"] for f in results) / max(len(results), 1), 1)
    warnings = sum(1 for f in results if f["mccabe"] > threshold)

    return {
        "file": str(filepath),
        "lines": line_count,
        "functions": results,
        "top5": by_mccabe,
        "avg_mccabe": avg_mccabe,
        "avg_cognitive": avg_cognitive,
        "total_functions": len(results),
        "warnings": warnings,
    }


def discover_php_files(root: Path) -> list[Path]:
    """Find all .php files, excluding vendor dirs."""
    files = []
    for f in root.rglob("*.php"):
        try:
            parts = f.relative_to(root).parts
        except ValueError:
            parts = f.parts
        if any(part in EXCLUDE_DIRS for part in parts):
            continue
        files.append(f)
    return sorted(set(files))


# ═══════════════════════════════════════════════════════════════════
# Output
# ═══════════════════════════════════════════════════════════════════


def print_report(results: list[dict], threshold: int) -> None:
    """Human-readable report."""
    total_files = len(results)
    total_funcs = sum(r.get("total_functions", 0) for r in results)
    total_warnings = sum(r.get("warnings", 0) for r in results)

    # Collect all functions for global top 10
    all_funcs = []
    for r in results:
        for f in r.get("functions", []):
            all_funcs.append({"file": r["file"], **f})
    global_top10 = sorted(all_funcs, key=lambda f: f["mccabe"], reverse=True)[:10]

    for report in results:
        filepath = report["file"]
        funcs = report.get("functions", [])
        top5 = report.get("top5", [])
        warnings = report.get("warnings", 0)

        status = "⚠" if warnings > 0 else "✅"
        print(f"\n{'=' * 70}")
        print(f" {status} {filepath}")
        print(f"{'=' * 70}")
        print(f"   Lines: {report['lines']}  |  Functions: {report['total_functions']}")
        print(f"   Avg McCabe: {report['avg_mccabe']}  |  Avg Cognitive: {report['avg_cognitive']}")
        print(f"   Warnings (> {threshold}): {warnings}")

        if top5:
            print(f"\n   Top 5 most complex:")
            for f in top5:
                bar = "█" * min(f["mccabe"], 40)
                print(f"     {f['name']:<30s} McCabe {f['mccabe']:3d}  Cog {f['cognitive']:5.1f}  {bar}  [{f['status']}]")
        else:
            print(f"   No functions found")

    # Grand summary
    print(f"\n{'=' * 70}")
    print(f" PHP COMPLEXITY SUMMARY")
    print(f"{'=' * 70}")
    print(f"   Files analyzed:      {total_files}")
    print(f"   Total functions:     {total_funcs}")
    print(f"   Avg McCabe:          {round(sum(f['mccabe'] for f in all_funcs) / max(len(all_funcs), 1), 1)}")
    print(f"   Warnings (> {threshold}):    {total_warnings}")

    if global_top10:
        print(f"\n   Global Top 10 most complex:")
        for f in global_top10:
            fname = Path(f["file"]).name
            bar = "█" * min(f["mccabe"], 30)
            print(f"     {f['name']:<25s} McCabe {f['mccabe']:3d}  [{fname}] {bar}")

    print()


def print_json(results: list[dict], threshold: int) -> None:
    """JSON output."""
    all_funcs = []
    for r in results:
        for f in r.get("functions", []):
            all_funcs.append({"file": r["file"], **f})

    global_top10 = sorted(all_funcs, key=lambda f: f["mccabe"], reverse=True)[:10]

    output = {
        "threshold": threshold,
        "summary": {
            "total_files": len(results),
            "total_functions": sum(r.get("total_functions", 0) for r in results),
            "total_lines": sum(r.get("lines", 0) for r in results),
            "warnings": sum(r.get("warnings", 0) for r in results),
            "avg_mccabe": round(sum(f["mccabe"] for f in all_funcs) / max(len(all_funcs), 1), 1),
        },
        "global_top10": global_top10,
        "files": [],
    }

    for report in results:
        output["files"].append({
            "file": report["file"],
            "lines": report["lines"],
            "total_functions": report["total_functions"],
            "avg_mccabe": report["avg_mccabe"],
            "avg_cognitive": report["avg_cognitive"],
            "warnings": report.get("warnings", 0),
            "functions": report.get("functions", []),
            "top5": report.get("top5", []),
        })

    print(json.dumps(output, indent=2, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="php_complexity.py - PHP cyclomatic complexity analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("path", help="PHP file or directory")
    parser.add_argument("--recursive", "-r", action="store_true", help="Recursive scan")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--threshold", "-t", type=int, default=DEFAULT_THRESHOLD,
                        help=f"McCabe warning threshold (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--version", action="version", version="php_complexity.py v1.0.0")

    args = parser.parse_args()
    target = Path(args.path)
    if not target.exists():
        print(f"'{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    if not args.json:
        print(f"\n📏 PHP Complexity v1.0.0 — analyzing: {target}")
        print(f"   Threshold: McCabe > {args.threshold}")
        print(f"{'=' * 70}")

    if target.is_file():
        if target.suffix != ".php":
            print(f"Not a .php file", file=sys.stderr)
            sys.exit(1)
        results = [analyze_php_file(target, args.threshold)]
    elif target.is_dir():
        files = discover_php_files(target) if args.recursive else sorted(target.glob("*.php"))
        if not files:
            print(f"No .php files found"); sys.exit(0)
        if not args.json:
            print(f"{len(files)} PHP file(s) found")
        results = [analyze_php_file(f, args.threshold) for f in files]
    else:
        print(f"Not a file or directory", file=sys.stderr); sys.exit(1)

    if args.json:
        print_json(results, args.threshold)
    else:
        print_report(results, args.threshold)


if __name__ == "__main__":
    main()
