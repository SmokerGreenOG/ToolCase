#!/usr/bin/env python3
"""
type_coverage.py — Meet type hint coverage in Python code.

Output:
  - % functies met type hints per file
  - Per-functie rapport
  - Trend over tijd (als --compare met vorige run)
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import ast
import json
import sys
from pathlib import Path
from collections import defaultdict

EXCLUDE_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".backups", ".rsi_reports", ".rsi_backups", "release",
    "build", "dist",
        ".self_improve_reports",
        })


def analyze_file(filepath: Path) -> dict:
    """Analyze type hints in a single Python file."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return {"file": str(filepath), "syntax_error": True}

    functions = 0
    typed_functions = 0
    params_total = 0
    params_typed = 0
    return_types = 0
    untyped: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions += 1
            func_params = len(node.args.args) + len(node.args.kwonlyargs)
            params_total += func_params
            typed_params = 0

            for arg in node.args.args + node.args.kwonlyargs:
                if arg.annotation:
                    typed_params += 1
                    params_typed += 1

            if node.returns:
                return_types += 1

            if typed_params < func_params or not node.returns:
                if typed_params == func_params and node.returns:
                    typed_functions += 1
                else:
                    untyped.append(node.name)
            else:
                typed_functions += 1

    coverage = (params_typed / max(1, params_total)) * 100
    func_coverage = (typed_functions / max(1, functions)) * 100

    return {
        "file": str(filepath),
        "functions": functions,
        "typed_functions": typed_functions,
        "func_coverage": round(func_coverage, 1),
        "params_total": params_total,
        "params_typed": params_typed,
        "param_coverage": round(coverage, 1),
        "return_types": return_types,
        "syntax_error": False,
        "untyped": untyped[:10],
    }


def scan_workspace(workspace: Path) -> list[dict]:
    """Scan all .py files."""
    results = []
    for fp in sorted(workspace.rglob("*.py")):
        if any(p.startswith(".") or p in EXCLUDE_DIRS for p in fp.parts):
            continue
        result = analyze_file(fp)
        results.append(result)
    return results


def print_report(results: list[dict]) -> None:
    """Print formatted report."""
    total_funcs = sum(r["functions"] for r in results if not r.get("syntax_error"))
    total_typed = sum(r["typed_functions"] for r in results if not r.get("syntax_error"))
    overall = (total_typed / max(1, total_funcs)) * 100

    print()
    print("=" * 60)
    print(" 📊 TYPE COVERAGE ANALYZER")
    print("=" * 60)
    print(f"   Overall: {overall:.0f}% ({total_typed}/{total_funcs} functions typed)")
    print(f"   Files: {len(results)}")
    print()

    # Sort by coverage ascending (worst first)
    sorted_results = sorted(
        [r for r in results if not r.get("syntax_error") and r["functions"] > 0],
        key=lambda r: r["func_coverage"]
    )

    print(f"   {'File':<40s} {'Func':>5s} {'Typed':>5s} {'Cover%':>7s}")
    print(f"   {'-'*58}")

    for r in sorted_results:
        fname = Path(r["file"]).name
        bar = "🔴" if r["func_coverage"] < 15 else "🟡" if r["func_coverage"] < 60 else "🟢"
        print(f"   {bar} {fname:<37s} {r['functions']:4d}  {r['typed_functions']:4d}  "
              f"{r['func_coverage']:6.1f}%")

    # Untyped functions in worst files
    print()
    print(f"   {'-'*58}")
    print(f"   TOP 10 UNTYPED FILES:")
    untyped_files = [r for r in sorted_results if r["func_coverage"] < 50]
    for r in untyped_files[:10]:
        fname = Path(r["file"]).name
        print(f"   📄 {fname} ({r['func_coverage']:.0f}%)")
        for func in r.get("untyped", [])[:5]:
            print(f"      → {func}()")

    # Grade
    print()
    if overall < 20:
        grade = "🔴 F — Weinig type hints"
    elif overall < 40:
        grade = "🟡 D — Matig"
    elif overall < 60:
        grade = "🟡 C — Voldoende"
    elif overall < 80:
        grade = "🟢 B — Goed"
    else:
        grade = "✅ A — Uitstekend"
    print(f"   Grade: {grade}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Type Coverage — Meet type hint coverage"
    )
    parser.add_argument("path", nargs="?", default=".", help="Workspace path")
    parser.add_argument("--json", "-j", action="store_true")
    parser.add_argument("--min-funcs", type=int, default=1,
                        help="Minimale functies om file mee te tellen")
    parser.add_argument("--version", action="version", version="type_coverage v1.0.0")

    args = parser.parse_args()
    target = Path(args.path).resolve()

    if not target.exists():
        print(f"❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    results = scan_workspace(target)
    results = [r for r in results if r.get("functions", 0) >= args.min_funcs]

    if args.json:
        total_funcs = sum(r["functions"] for r in results)
        total_typed = sum(r["typed_functions"] for r in results)
        print(json.dumps({
            "overall": round((total_typed / max(1, total_funcs)) * 100, 1),
            "files": len(results),
            "results": [{
                "file": Path(r["file"]).name,
                "functions": r["functions"],
                "typed_functions": r["typed_functions"],
                "func_coverage": r["func_coverage"],
            } for r in results]
        }, indent=2, ensure_ascii=False))
    else:
        print_report(results)


if __name__ == "__main__":
    main()
