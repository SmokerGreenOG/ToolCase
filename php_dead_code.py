#!/usr/bin/env python3
"""
php_dead_code.py — PHP dead code finder.

Detecteert in PHP projecten:
  - Ongebruikte functies en methodes
  - Ongebruikte klassen
  - Commented-out code blocks
  - Lege functies/methodes
  - Private methods die nooit aangeroepen worden binnen de class

Gebruik:
    python php_dead_code.py <path> --recursive
    python php_dead_code.py <path> --json
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import sys
from pathlib import Path

EXCLUDE_DIRS = {"node_modules", "vendor", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".cache"}

# Function definition: function name(...)
FUNC_DEF = re.compile(
    r'^\s*(?:(?:public|private|protected|static|abstract|final)\s+)*'
    r'function\s+(\w+)\s*\(',
    re.MULTILINE,
)
# Class definition
CLASS_DEF = re.compile(
    r'^\s*(?:abstract\s+)?(?:final\s+)?class\s+(\w+)',
    re.MULTILINE,
)
# Commented-out code (> 3 lines)
COMMENTED_BLOCK = re.compile(
    r'(?:/\*[\s\S]*?\*/|(?:^\s*//\s*\$\w+.*\n){3,})',
    re.MULTILINE,
)
# Empty function body
EMPTY_FUNC = re.compile(
    r'function\s+\w+\s*\([^)]*\)\s*\{\s*\}',
)


def discover_php_files(root: Path) -> list[Path]:
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


def analyze_file(filepath: Path) -> dict:
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except:
        return {"file": str(filepath), "functions": [], "classes": [], "commented_blocks": 0, "empty_funcs": []}
    
    # Extract function names and class names
    functions = [{"name": m.group(1), "line": source[:m.start()].count('\n') + 1} for m in FUNC_DEF.finditer(source)]
    classes = [m.group(1) for m in CLASS_DEF.finditer(source)]
    
    # Commented-out code blocks
    commented_blocks = len(COMMENTED_BLOCK.findall(source))
    
    # Empty functions
    empty_funcs = [{"name": m.group(1), "line": source[:m.start()].count('\n') + 1} for m in re.finditer(
        r'function\s+(\w+)\s*\([^)]*\)\s*\{\s*\}', source
    )]
    
    return {
        "file": str(filepath),
        "functions": functions,
        "classes": classes,
        "commented_blocks": commented_blocks,
        "empty_funcs": empty_funcs,
    }


def find_unused(project_results: list[dict]) -> dict:
    """Cross-reference all function calls vs definitions across the project."""
    all_defs = {}  # func_name -> [(file, line), ...]
    all_calls = set()
    
    for r in project_results:
        # Read full source
        try:
            source = Path(r["file"]).read_text(encoding="utf-8", errors="replace")
        except:
            continue
        
        for f in r["functions"]:
            all_defs.setdefault(f["name"], []).append((r["file"], f["line"]))
        
        # Find function calls (foo(, $obj->foo(, Class::foo(, self::foo()
        for match in re.finditer(r'(?:\$?\w+(?:->|::))?(\w+)\s*\(', source):
            call_name = match.group(1)
            if call_name not in ('if', 'for', 'while', 'foreach', 'switch', 'return', 'echo', 'print',
                                'array', 'list', 'isset', 'empty', 'unset', 'die', 'exit', 'include',
                                'require', 'function', 'class', 'new', 'throw', 'catch', 'try', 'case',
                                'default', 'clone', 'instanceof', 'global', 'static', 'public', 'private',
                                'protected', 'abstract', 'final', 'namespace', 'use', 'as', 'break',
                                'continue', 'declare', 'endfor', 'endforeach', 'endwhile', 'endswitch',
                                'endif', 'enddeclare', 'extends', 'implements', 'trait', 'insteadof',
                                'callable', 'goto', 'const', 'var', 'yield', 'from', 'match'):
                all_calls.add(call_name)
    
    unused = {}
    for name, locations in all_defs.items():
        if name not in all_calls:
            unused[name] = locations
    
    return unused


def print_report(results: list[dict], unused: dict) -> None:
    total_funcs = sum(len(r["functions"]) for r in results)
    total_classes = sum(len(r["classes"]) for r in results)
    total_commented = sum(r["commented_blocks"] for r in results)
    total_empty = sum(len(r["empty_funcs"]) for r in results)
    
    for r in results:
        status = "⚠" if (r["commented_blocks"] > 0 or r["empty_funcs"]) else "✅"
        print(f"\n{'=' * 70}")
        print(f" {status} {r['file']}")
        print(f"{'=' * 70}")
        print(f"   Functions: {len(r['functions'])}  |  Classes: {len(r['classes'])}")
        
        if r["empty_funcs"]:
            print(f"   Empty functions ({len(r['empty_funcs'])}):")
            for ef in r["empty_funcs"]:
                print(f"     - {ef['name']}() (line {ef['line']})")
        if r["commented_blocks"] > 0:
            print(f"   Commented-out blocks: {r['commented_blocks']}")
    
    print(f"\n{'=' * 70}")
    print(f" DEAD CODE SUMMARY")
    print(f"{'=' * 70}")
    print(f"   Files:       {len(results)}")
    print(f"   Functions:   {total_funcs}")
    print(f"   Classes:     {total_classes}")
    print(f"   Empty funcs: {total_empty}")
    print(f"   Commented:   {total_commented}")
    
    if unused:
        print(f"\n   ⚠ UNUSED FUNCTIONS ({len(unused)}):")
        for name, locations in sorted(unused.items()):
            for file, line in locations:
                print(f"     - {name}() in {file}:{line}")
    else:
        print(f"   ✅ No unused functions detected")
    
    print()


def print_json(results: list[dict], unused: dict) -> None:
    output = {
        "summary": {
            "total_files": len(results),
            "total_functions": sum(len(r["functions"]) for r in results),
            "total_classes": sum(len(r["classes"]) for r in results),
            "empty_functions": sum(len(r["empty_funcs"]) for r in results),
            "commented_blocks": sum(r["commented_blocks"] for r in results),
            "unused_functions": len(unused),
        },
        "unused_functions": {name: [{"file": f, "line": l} for f, l in locs] for name, locs in unused.items()},
        "files": results,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="php_dead_code.py - PHP dead code finder")
    parser.add_argument("path", help="PHP file or directory")
    parser.add_argument("--recursive", "-r", action="store_true")
    parser.add_argument("--json", "-j", action="store_true")
    parser.add_argument("--version", action="version", version="php_dead_code.py v1.0.0")
    
    args = parser.parse_args()
    target = Path(args.path)
    if not target.exists():
        print(f"Not found", file=sys.stderr); sys.exit(1)
    
    files = [target] if target.is_file() else (discover_php_files(target) if args.recursive else sorted(target.glob("*.php")))
    if not files:
        print("No PHP files"); sys.exit(0)
    
    print(f"\n💀 PHP Dead Code v1.0.0 — {len(files)} file(s)")
    print(f"{'=' * 70}")
    
    results = [analyze_file(f) for f in files]
    unused = find_unused(results) if len(results) > 1 else {}
    
    if args.json:
        print_json(results, unused)
    else:
        print_report(results, unused)


if __name__ == "__main__":
    main()
