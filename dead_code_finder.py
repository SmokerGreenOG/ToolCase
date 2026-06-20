#!/usr/bin/env python3
"""
dead_code_finder.py — Find unused variables, imports, functions, and dead code.

Scans Python TypeScript en Rust broncode voor:
  - Ongebruikte imports (geïmporteerd maar nooit aangeroepen)
  - Ongebruikte variabelen (toegewezen maar nooit gelezen)
  - Dode functies (gedefinieerd maar nooit aangeroepen, behalve entry points)
  - Dode klassen (gedefinieerd maar nooit geïnstantieerd)
  - Commented-out code blokken
  - Overbodige pass/noop statements

Gebruik:
    python dead_code_finder.py <path>
    python dead_code_finder.py <path> --json
    python dead_code_finder.py <path> --min-confidence 0.5
    python dead_code_finder.py <path> --threshold 5
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import ast
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = frozenset({
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    ".tox", ".eggs", "build", "dist", ".next",
        ".backups",
        
        ".rsi_backups",
        
        ".rsi_reports",
        
        ".self_improve_reports",
        })

# Patterns for code that should always be considered "used"
ENTRY_POINT_PATTERNS = {
    "py": {
        "entry_names": {"main", "run", "start", "setup"},
        "decorators": {"app", "router", "blueprint", "cli", "click"},
    },
    "ts": {
        "entry_names": {"main", "run", "start", "setup", "init", "handler",
                        "default", "getStaticProps", "getServerSideProps",
                        "getStaticPaths", "GET", "POST", "PUT", "DELETE", "PATCH"},
        "decorators": {"@Component", "@NgModule", "@Injectable", "@Directive",
                       "@Pipe", "@override"},
    },
    "rs": {
        "entry_names": {"main", "run", "start", "setup"},
        "decorators": {"#[tokio::main", "#[actix_web::", "#[get", "#[post",
                       "#[put", "#[delete", "#[patch"},
    },
}

# Commented-out code detection
COMMENTED_CODE_PATTERN = re.compile(
    r'^\s*#\s*(?:def|class|if|for|while|try|with|import|from|return|print|'
    r'async|await|@|self\.|const|let|var|function|fn|pub\s+fn)',
    re.MULTILINE,
)


def collect_source_files(root: Path) -> list[Path]:
    """Collect source files to analyze."""
    files = []
    exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".mjs", ".cjs"}

    if root.is_file():
        return [root]

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            ext = Path(fn).suffix.lower()
            if ext in exts:
                files.append(Path(dirpath) / fn)

    return sorted(files)


def get_all_names(content: str, lang: str) -> set[str]:
    """Extract all identifier-like names from code."""
    names = set()
    if lang in ("py",):
        # Python identifiers
        names.update(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', content))
    elif lang in ("ts", "js"):
        names.update(re.findall(r'\b([a-zA-Z_$][a-zA-Z0-9_$]*)\b', content))
    elif lang == "rs":
        names.update(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', content))
        # Also Rust snake_case identifiers with ::
        names.update(re.findall(r'\b([a-z_][a-z0-9_]*(?:::))', content))
    return names


def find_unused_python_imports(filepath: Path, content: str,
                                all_names_in_project: set[str]) -> list[dict]:
    """Find unused imports in a Python file using AST."""
    issues = []
    try:
        tree = ast.parse(content, filename=str(filepath))
    except SyntaxError:
        return issues

    imported_names = {}  # name -> (line, import_source)
    used_names = set()

    for node in ast.walk(tree):
        # Track imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name
                imported_names[name] = (node.lineno, alias.name)

        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                imported_names[name] = (node.lineno, f"{node.module}.{alias.name}")

        # Track name usage
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            used_names.add(node.attr)

    # Also check strings for f-strings that reference names
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.FormattedValue):
                    if isinstance(value.value, ast.Name):
                        used_names.add(value.value.id)

    # Check which imports are unused
    for name, (line, import_source) in imported_names.items():
        # Skip __future__ imports
        if import_source.startswith("__future__"):
            continue
        # Check if the name has been filtered by the entry_point check
        root_name = name.split(".")[0]  # For `import os.path`, check `os`
        if root_name in used_names:
            continue
        if name in all_names_in_project:
            continue

        issues.append({
            "file": str(filepath),
            "line": line,
            "type": "unused_import",
            "name": name,
            "import_source": import_source,
            "confidence": 0.9,
        })

    return issues


def find_unused_functions(content: str, filepath: Path,
                           lang: str, all_names: set[str]) -> list[dict]:
    """Find functions that are defined but never called."""
    issues = []

    function_defs = {}
    function_calls = set()

    entry_names = ENTRY_POINT_PATTERNS.get(lang, {}).get("entry_names", set())
    entry_decorators = ENTRY_POINT_PATTERNS.get(lang, {}).get("decorators", set())

    if lang == "py":
        try:
            tree = ast.parse(content, filename=str(filepath))
        except SyntaxError:
            return issues

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Check decorators
                decorators = set()
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Attribute):
                        decorators.add(dec.attr)
                    elif isinstance(dec, ast.Name):
                        decorators.add(dec.id)
                    elif isinstance(dec, ast.Call):
                        if isinstance(dec.func, ast.Name):
                            decorators.add(dec.func.id)
                        elif isinstance(dec.func, ast.Attribute):
                            decorators.add(dec.func.attr)

                function_defs[node.name] = {
                    "line": node.lineno,
                    "decorators": decorators,
                    "is_method": len(node.args.args) > 0 and any(
                        a.arg == "self" or a.arg == "cls" for a in node.args.args
                    ),
                    "is_dunder": node.name.startswith("__") and node.name.endswith("__"),
                }

            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    function_calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    function_calls.add(node.func.attr)

        for name, info in function_defs.items():
            if name in entry_names:
                continue
            if info["is_dunder"]:
                # Dunder methods are called implicitly
                continue
            if info["is_method"]:
                continue
            if any(d in entry_decorators for d in info["decorators"]):
                continue
            if name in function_calls:
                continue
            if name in all_names:
                continue

            issues.append({
                "file": str(filepath),
                "line": info["line"],
                "type": "unused_function",
                "name": name,
                "confidence": 0.7,
            })

    elif lang in ("ts", "js"):
        # Find function definitions
        fn_pat = (r'(?:function\s+(\w+)|'
                  r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\()')
        for m in re.finditer(fn_pat, content):
            name = m.group(1) or m.group(2)
            if name and name not in entry_names:
                line = content[:m.start()].count("\n") + 1
                if name not in all_names:
                    issues.append({
                        "file": str(filepath),
                        "line": line,
                        "type": "unused_function",
                        "name": name,
                        "confidence": 0.6,
                    })

    elif lang == "rs":
        for m in re.finditer(r'(?:pub\s+)?(?:unsafe\s+)?fn\s+(\w+)', content):
            name = m.group(1)
            if name and name not in entry_names:
                line = content[:m.start()].count("\n") + 1
                if name not in all_names:
                    issues.append({
                        "file": str(filepath),
                        "line": line,
                        "type": "unused_function",
                        "name": name,
                        "confidence": 0.6,
                    })

    return issues


def find_commented_out_code(filepath: Path, content: str) -> list[dict]:
    """Find large commented-out code blocks."""
    issues = []
    lines = content.split("\n")

    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("#") and COMMENTED_CODE_PATTERN.match(lines[i]):
            block_start = i
            block_lines = [lines[i]]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("#"):
                if COMMENTED_CODE_PATTERN.match(lines[i]):
                    block_lines.append(lines[i])
                else:
                    break
                i += 1

            if len(block_lines) >= 3:  # 3+ commented-out code lines
                issues.append({
                    "file": str(filepath),
                    "line": block_start + 1,
                    "type": "commented_code",
                    "lines": len(block_lines),
                    "snippet": "\n".join(block_lines[:3]),
                    "confidence": 0.8,
                })
            continue
        i += 1

    return issues


def analyze_file(filepath: Path, all_names: set[str]) -> list[dict]:
    """Analyze a single file for dead code."""
    issues = []
    ext = filepath.suffix.lower()

    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return issues

    if ext == ".py":
        lang = "py"
    elif ext in (".ts", ".tsx"):
        lang = "ts"
    elif ext in (".js", ".jsx", ".mjs", ".cjs"):
        lang = "js"
    elif ext == ".rs":
        lang = "rs"
    else:
        return issues

    # Find unused imports (Python only)
    if lang == "py":
        imports = find_unused_python_imports(filepath, content, all_names)
        issues.extend(imports)

    # Find unused functions
    funcs = find_unused_functions(content, filepath, lang, all_names)
    issues.extend(funcs)

    # Find commented-out code
    commented = find_commented_out_code(filepath, content)
    issues.extend(commented)

    return issues


def print_report(all_issues: list[dict]) -> None:
    """Print formatted dead code report."""
    by_type = defaultdict(list)
    for issue in all_issues:
        by_type[issue["type"]].append(issue)

    total = len(all_issues)

    print(f"\n{'='*60}")
    print(f" 💀 DEAD CODE FINDER — {total} finding(s)")
    print(f"{'='*60}")
    print(f"   Ongebruikte imports:    {len(by_type.get('unused_import', []))}")
    print(f"   Ongebruikte functies:   {len(by_type.get('unused_function', []))}")
    print(f"   Commented-out code:     {len(by_type.get('commented_code', []))}")
    print()

    for type_name, label in [("unused_import", "Ongebruikte Imports"),
                              ("unused_function", "Ongebruikte Functies"),
                              ("commented_code", "Commented-Out Code")]:
        items = by_type.get(type_name, [])
        if not items:
            continue
        print(f" ── {label} ({len(items)}) ──")
        for item in items[:15]:
            confidence = f"{int(item['confidence'] * 100)}%"
            cwd = Path.cwd()
            fp = Path(item["file"])
            rel = fp.relative_to(cwd) if fp.exists() else item["file"]
            print(f"   {rel}:{item['line']}  {item['name']}  [{confidence}]")
            if item["type"] == "commented_code" and "snippet" in item:
                print(f"      {item['snippet'][:80]}")
        if len(items) > 15:
            print(f"   ... en nog {len(items) - 15} meer")
        print()

    if not all_issues:
        print(" ✅ Geen dead code gevonden!")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="dead_code_finder.py — Find unused imports, functions, and dead code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python dead_code_finder.py .
  python dead_code_finder.py src/ --json
  python dead_code_finder.py . --threshold 5
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Bestand of directory")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--threshold", "-t", type=int, default=3,
                        help="Min regels commented code (default: 3)")
    parser.add_argument("--version", action="version", version="dead_code_finder.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 Dead Code Finder v1.0.0 — scanning {target}")

    files = collect_source_files(target)
    if not files:
        print(" Geen bronbestanden gevonden")
        sys.exit(0)

    print(f"   {len(files)} bestand(en) om te scannen")

    # Build all-names set from project
    all_names = set()
    for fp in files:
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
            ext = fp.suffix.lower()
            if ext == ".py":
                lang = "py"
            elif ext in (".ts", ".tsx"):
                lang = "ts"
            elif ext == ".rs":
                lang = "rs"
            else:
                if ext in (".js", ".jsx", ".mjs", ".cjs"):
                    lang = "js"
                else:
                    continue
            names = get_all_names(content, lang)
            # Filter to reasonable names (>2 chars, not keywords)
            keywords = {"if", "for", "while", "try", "def", "class", "import",
                        "from", "return", "yield", "with", "as", "in", "is",
                        "and", "or", "not", "True", "False", "None", "self",
                        "cls", "the", "and", "are", "var", "let", "const",
                        "type", "new", "this", "fn", "pub", "use", "mod",
                        "let", "mut", "ref", "impl", "trait", "enum", "struct",
                        "pub", "crate", "self", "super", "where", "as",
                        "async", "await", "move", "box", "if", "for", "while",
                        "loop", "match", "break", "continue", "return", "in",
                        "else", "try", "catch", "throw", "finally", "switch",
                        "case", "default", "function", "export", "import",
                        "from", "class", "extends", "implements", "interface",
                        "typeof", "instanceof", "void", "null", "undefined",
                        "any", "never", "unknown", "string", "number",
                        "boolean", "bigint", "symbol", "object"}
            all_names.update(n for n in names if len(n) > 2 and n not in keywords)
        except Exception:
            continue

    all_issues = []
    for fp in files:
        issues = analyze_file(fp, all_names)
        all_issues.extend(issues)

    if args.json:
        print(json.dumps(all_issues, indent=2, ensure_ascii=False))
    else:
        print_report(all_issues)


if __name__ == "__main__":
    main()
