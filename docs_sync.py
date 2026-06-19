#!/usr/bin/env python3
"""
docs_sync.py — Check whether README/docs match the actual code.

Detects mismatches between documentation and source code:
  - Features described in docs that don't exist in code
  - Code features not documented in README/docs
  - Commands in docs that don't actually exist
  - Install instructions missing required dependencies
  - Claims (e.g. "terminal support", "file editor") contradicted by code

Checks README.md and docs/*.md against Python source files.

Usage:
    python docs_sync.py <path>
    python docs_sync.py <path> --json
    python docs_sync.py <path> --verbose

Exit codes:
    0 — No issues (docs match code)
    1 — Issues found (docs out of sync with code)
    2 — Error (path not found, etc.)
"""

from __future__ import annotations

__maker__ = "SmokerGreenOG"

import _protect

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv", "build",
    "dist", ".next", "out", "coverage", ".vscode", ".idea", "release",
    ".pytest_cache", ".cache", ".backups", "_test_contract", "_test_patches",
    "demo", "logs",
})

EXCLUDE_FILES = frozenset({
    "__init__.py", "_test_changelog.py", "_test_extract.py",
    "tools_config.json",
})

# Patterns for extracting importable/executable names from source
TOOL_IMPORT_PATTERN = re.compile(
    r'from\s+(\S+)\s+import\s+(\S+)'
)

FUNCTION_DEF_PATTERN = re.compile(
    r'^async?\s+def\s+(\w+)'
)

CLASS_DEF_PATTERN = re.compile(
    r'^class\s+(\w+)'
)

# Flag names mentioned in argparse definitions
ARGPARSE_FLAG_PATTERN = re.compile(
    r'--([a-z][a-z0-9_-]*)'
)

# Look for "add_argument" calls that define tool flags
ADD_ARGUMENT_PATTERN = re.compile(
    r'add_argument\s*\([\s\S]*?--([a-z][a-z0-9_-]*)'
)

# Terminal endpoint pattern (Flask/FastAPI/Django route decorators)
TERMINAL_ENDPOINT_PATTERN = re.compile(
    r'@(?:app|router|blueprint)\.(?:route|get|post|put|delete|patch)\('
)

# Command definition patterns
COMMAND_DEF_PATTERN = re.compile(
    r'(?:python\s+\S+\.py\s+|--[a-z][a-z0-9_-]+\s+)',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------


def collect_python_files(root: Path) -> list[Path]:
    """Recursively collect all .py files under root, excluding known dirs."""
    files: list[Path] = []
    for p in root.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        if p.name in EXCLUDE_FILES:
            continue
        files.append(p)
    return sorted(files)


def read_text_file(path: Path) -> str:
    """Read text file content, return empty string on error."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Source Code Analysis
# ---------------------------------------------------------------------------


def extract_features_from_source(files: list[Path]) -> dict[str, Any]:
    """Extract features, commands, and identifiers from Python source files.

    Returns:
        {
            "tools": [str],           # tool names (filenames without .py)
            "flags": [str],           # --flag arguments defined in argparse
            "functions": [str],       # top-level function names
            "classes": [str],         # top-level class names
            "has_terminal_endpoint": bool,  # any @app.route etc.
            "has_file_editor": bool,        # any file write/edit patterns
            "imported_tools": [str],       # tools imported internally
            "cli_commands": [str],         # python tool commands found
        }
    """
    tools: set[str] = set()
    flags: set[str] = set()
    functions: set[str] = set()
    classes: set[str] = set()
    has_terminal_endpoint = False
    has_file_editor = False
    imported_tools: set[str] = set()
    cli_commands: set[str] = set()

    for fp in files:
        name_stem = fp.stem
        if name_stem != "__init__":
            tools.add(name_stem)

        source = read_text_file(fp)
        if not source:
            continue

        # Check for terminal endpoints (Flask/FastAPI routes)
        if TERMINAL_ENDPOINT_PATTERN.search(source):
            has_terminal_endpoint = True

        # Check for file editing patterns (open with write, file I/O operations)
        if re.search(r'\bopen\s*\([^)]*["\']w["\']', source) or \
           re.search(r'\.write\s*\(', source) or \
           re.search(r'(?:shutil|os)\.(?:copy|move|rename|remove)', source):
            has_file_editor = True

        # Extract function definitions
        for match in re.finditer(r'^async?\s+def\s+(\w+)', source, re.MULTILINE):
            functions.add(match.group(1))

        # Extract class definitions
        for match in re.finditer(r'^class\s+(\w+)', source, re.MULTILINE):
            classes.add(match.group(1))

        # Extract argparse --flags
        for match in ADD_ARGUMENT_PATTERN.finditer(source):
            flags.add(match.group(1))

        # Also check for --flag in string literals
        for match in ARGPARSE_FLAG_PATTERN.finditer(source):
            flag = match.group(1)
            if flag not in ("help", "json", "verbose", "recursive", "version",
                            "auto-fix", "list-tools", "json-config", "all",
                            "code", "threshold", "min-severity", "exclude"):
                flags.add(flag)

        # Check for import of tool modules
        for match in re.finditer(r'^import\s+(\w+)', source, re.MULTILINE):
            imported_tools.add(match.group(1))
        for match in re.finditer(r'^from\s+(\w+)', source, re.MULTILINE):
            imported_tools.add(match.group(1))

        # Extract CLI command patterns
        for match in re.finditer(r'python\s+(\S+\.py)\s+', source):
            cli_commands.add(match.group(1))

    return {
        "tools": sorted(tools),
        "flags": sorted(flags),
        "functions": sorted(functions),
        "classes": sorted(classes),
        "has_terminal_endpoint": has_terminal_endpoint,
        "has_file_editor": has_file_editor,
        "imported_tools": sorted(imported_tools),
        "cli_commands": sorted(cli_commands),
    }


# ---------------------------------------------------------------------------
# Documentation Analysis
# ---------------------------------------------------------------------------


def extract_features_from_readme(content: str) -> dict[str, Any]:
    """Extract feature claims, commands, and tool names from README.md.

    Returns:
        {
            "mentioned_tools": [str],       # tool names mentioned
            "mentioned_commands": [str],     # CLI commands mentioned
            "feature_claims": [str],         # feature descriptions
            "mentions_terminal": bool,       # mentions terminal support
            "mentions_file_editor": bool,    # mentions file editing
            "install_deps": [str],           # install dependencies mentioned
        }
    """
    mentioned_tools: set[str] = set()
    mentioned_commands: set[str] = set()
    feature_claims: list[str] = []
    install_deps: set[str] = set()
    mentions_terminal = False
    mentions_file_editor = False

    # Extract tool names from markdown table rows and code blocks
    for match in re.finditer(
        r'\|\s*[:🌀🛡️🌍🩺🗺️🔗💀📋🧪👁️🔄📦📊🧠🎨🔍🔧🛠️📏]?\s*\*{0,2}([\w.-]+(?:\.py)?)\*{0,2}\s*\|',
        content,
    ):
        name = match.group(1).strip()
        if name.lower() in ("tool", "", "toolcase"):
            continue
        # Skip table separator rows (e.g. ------ or ----------)
        if re.match(r'^-+$', name):
            continue
        # Skip known table header words
        if name.lower() in ("commando", "beschrijving", "analyse tools",
                            "structure & state tools", "legacy tools (via improve.py --all)",
                            "tool", "description", "command", "name"):
            continue
        # Only capture things that look like filenames or identifiers
        if name.replace("-", "_").replace(".", "_").isidentifier():
            if name.endswith(".py"):
                mentioned_tools.add(name.replace(".py", ""))
            elif len(name) > 1 and name[0].isalpha():
                mentioned_tools.add(name)

    # Extract tool names from bold markers in the format **name.py**
    for match in re.finditer(
        r'\*\*([\w.-]+\.py)\*\*',
        content,
    ):
        name = match.group(1).replace(".py", "")
        if name.lower() not in ("tool", ""):
            mentioned_tools.add(name)

    # Extract commands (python some_tool.py ...)
    for match in re.finditer(r'python\s+([\w.-]+\.py)', content):
        mentioned_commands.add(match.group(1).replace(".py", ""))

    # Extract --flags from command examples
    for match in re.finditer(r'--([\w-]+)\b', content):
        flag = match.group(1)
        if flag not in ("help", "recursive", "all", "json", "version"):
            mentioned_commands.add(f"--{flag}")

    # Check feature claims
    terminal_patterns = [
        r'terminal\s+(support|endpoint|api|command)',
        r'\bCLI\b',
        r'command[-\s]line',
    ]
    for pat in terminal_patterns:
        if re.search(pat, content, re.IGNORECASE):
            mentions_terminal = True

    file_editor_patterns = [
        r'file\s+editor',
        r'file\s+(write|edit|modify)',
        r'\beditor\b',
    ]
    for pat in file_editor_patterns:
        if re.search(pat, content, re.IGNORECASE):
            mentions_file_editor = True

    # Extract install dependencies
    install_section = ""
    install_match = re.search(
        (r'(?:##\s*(?:Install|Installatie|Setup|Getting'
               r'Started|Quick Start|Snel starten)[^\n]*)(.*?)(?=##\s|\Z)'),
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if install_match:
        install_section = install_match.group(1)
        # Look for pip/apt/brew/cargo etc.
        for dep in re.finditer(r'(pip|npm|yarn|pnpm|apt|brew|choco|cargo)\s+(install|add)\s+(\S+)', install_section, re.IGNORECASE):
            install_deps.add(dep.group(3).strip())
        for dep in re.finditer(r'requires?\s+(Python\s*[\d.]+|Node\.js\s*[\d.]+|Rust\s*[\d.]+)', install_section, re.IGNORECASE):
            install_deps.add(dep.group(1).strip())

    # Extract feature claims from list items
    for match in re.finditer(r'[-*]\s+\*\*([^*]+)\*\*', content):
        claim = match.group(1).strip()
        if claim and len(claim) < 100:
            feature_claims.append(claim)

    # Also extract table cells with descriptions
    in_table = False
    for line in content.split("\n"):
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 3 and cells[0] and cells[2]:
                feature_claims.append(f"{cells[0]}: {cells[2]}")

    return {
        "mentioned_tools": sorted(mentioned_tools),
        "mentioned_commands": sorted(mentioned_commands),
        "feature_claims": feature_claims,
        "mentions_terminal": mentions_terminal,
        "mentions_file_editor": mentions_file_editor,
        "install_deps": sorted(install_deps),
    }


def extract_features_from_docs(docs_path: Path) -> list[dict[str, Any]]:
    """Extract features from all markdown files in the docs/ folder."""
    results: list[dict[str, Any]] = []
    if not docs_path.is_dir():
        return results

    for md_file in sorted(docs_path.rglob("*.md")):
        content = read_text_file(md_file)
        if not content:
            continue
        feats = extract_features_from_readme(content)
        feats["file"] = str(md_file.relative_to(docs_path.parent))
        results.append(feats)

    return results


# ---------------------------------------------------------------------------
# Comparison / Sync Check
# ---------------------------------------------------------------------------


def check_docs_sync(
    root: Path,
    source_features: dict[str, Any],
    readme_content: str,
    doc_features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare documentation features against actual code features.

    Returns a list of issues, each with:
        {
            "type": str,        # issue category
            "severity": str,    # "error" | "warning" | "info"
            "message": str,     # human-readable description
            "detail": str,      # extra context
        }
    """
    issues: list[dict[str, Any]] = []

    actual_tools = set(source_features["tools"])
    actual_flags = set(source_features["flags"])
    has_terminal = source_features["has_terminal_endpoint"]
    has_file_editor = source_features["has_file_editor"]

    # 1. Check README tool claims against actual files
    all_doc_tools: set[str] = set()
    all_doc_commands: set[str] = set()
    all_doc_feature_claims: list[str] = []

    readme_feats = extract_features_from_readme(readme_content)
    all_doc_tools.update(readme_feats["mentioned_tools"])
    all_doc_commands.update(readme_feats["mentioned_commands"])
    all_doc_feature_claims.extend(readme_feats["feature_claims"])

    for d in doc_features:
        all_doc_tools.update(d.get("mentioned_tools", []))
        all_doc_commands.update(d.get("mentioned_commands", []))
        all_doc_feature_claims.extend(d.get("feature_claims", []))

    # 1a. Tools mentioned in docs that don't exist in source
    for tool in sorted(all_doc_tools):
        if tool == "improve":
            continue  # improve.py is the main entry point, always present
        if tool not in actual_tools:
            # Check if it's a filename reference
            found_similar = [t for t in actual_tools if tool.replace("-", "_") in t or t in tool.replace("_", "-")]
            detail = f"Similar tools: {', '.join(found_similar)}" if found_similar else "Not found in source code"
            issues.append({
                "type": "doc_claims_missing_tool",
                "severity": "error",
                "message": f"Docs mention tool '{tool}' but no corresponding source file exists",
                "detail": detail,
            })

    # 1b. Actual tools not mentioned in docs
    # Build list of tools the docs DO mention (from README tool tables)
    readme_tool_list = _extract_tool_table_names(readme_content)
    tools_not_in_docs = [
        t for t in sorted(actual_tools)
        if t not in readme_tool_list
        and t not in ("__init__", "_test_changelog", "_test_extract",
                       "improve", "tools_config")
        and not t.startswith("_")
    ]
    for tool in tools_not_in_docs:
        issues.append({
            "type": "code_has_undocumented_tool",
            "severity": "warning",
            "message": f"Source file '{tool}.py' exists but is not mentioned in README/docs",
            "detail": "Consider adding it to the documentation",
        })

    # 2. Check terminal support claim
    if readme_feats["mentions_terminal"] and not has_terminal:
        issues.append({
            "type": "terminal_claim_mismatch",
            "severity": "error",
            "message": ("README claims terminal/CLI support but source code has no terminal"
                   "endpoint"),
            "detail": "No @app.route, @router.get, or similar endpoint decorators found",
        })

    # 3. Check file editor claim
    if readme_feats["mentions_file_editor"] and not has_file_editor:
        issues.append({
            "type": "file_editor_claim_mismatch",
            "severity": "error",
            "message": ("README mentions file editing capability but source has no file write/modify"
                   "operations"),
            "detail": "No open(..., 'w') or file write patterns found in source code",
        })

    # 4. Check commands mentioned in docs exist in source
    for cmd in sorted(all_doc_commands):
        if cmd.startswith("--"):
            flag_name = cmd[2:]
            # Check if this flag exists in any argparse definition
            if flag_name not in actual_flags and flag_name not in (
                "help", "recursive", "version", "json", "verbose",
                "auto-fix", "list-tools", "json-config",
            ):
                # Check improve.py specifically (the dispatcher)
                improve_content = read_text_file(root / "improve.py")
                if f"--{flag_name}" not in improve_content:
                    issues.append({
                        "type": "doc_mentions_missing_command",
                        "severity": "error",
                        "message": f"Docs mention command '--{flag_name}' but it's not defined in any source file",
                        "detail": "No argparse add_argument found for this flag",
                    })
        elif cmd.endswith(".py") and cmd != "improve.py":
            cmd_name = cmd.replace(".py", "")
            if cmd_name not in actual_tools:
                issues.append({
                    "type": "doc_mentions_missing_command",
                    "severity": "error",
                    "message": f"Docs mention command 'python {cmd}' but '{cmd_name}.py' does not exist",
                    "detail": "Command referenced in documentation but file not found",
                })

    # 5. Check install deps (if README mentions dependencies)
    install_deps_mentioned = readme_feats["install_deps"]
    if install_deps_mentioned:
        # Verify each mentioned dep is actually used
        all_source = ""
        for fp in collect_python_files(root):
            all_source += read_text_file(fp) + "\n"
        for dep in install_deps_mentioned:
            dep_clean = dep.lower().replace("-", "_").replace(".", "_")
            if dep_clean not in all_source.lower():
                issues.append({
                    "type": "install_dep_not_found",
                    "severity": "warning",
                    "message": f"Install docs mention '{dep}' as a dependency but it's not imported/used in source",
                    "detail": "Possible outdated install instructions",
                })

    # 6. Check for feature claims that don't match code patterns
    feature_to_code_check = {
        "security": r"secret|api.key|password|token",
        "route": r"route",
        "test": r"test|unittest|pytest",
        "backup": r"backup|snapshot|\.bak",
        "changelog": r"changelog",
        "release": r"release|package",
        "log": r"log|logging",
        "error": r"traceback|error|exception",
        "dead.code": r"dead|unused|commented.out",
        "dependency": r"dep|dependency",
        "complexity": r"complexity|cognitive|cyclomatic",
        "env": r"env|environment|\.env",
        "permission": r"permission|audit|guard",
        "state": r"state|useState|store",
        "ui": r"ui|consistency|pattern",
    }

    # Check if certain feature claims in README have corresponding code patterns
    for claim in all_doc_feature_claims:
        claim_lower = claim.lower()
        for feature_key, code_pattern in feature_to_code_check.items():
            if feature_key.replace(".", " ") in claim_lower or \
               feature_key.replace(".", "_") in claim_lower:
                # Verify this feature exists in code
                code_found = False
                for fp in collect_python_files(root):
                    content = read_text_file(fp)
                    if re.search(code_pattern, content, re.IGNORECASE):
                        code_found = True
                        break
                if not code_found:
                    issues.append({
                        "type": "feature_claim_mismatch",
                        "severity": "warning",
                        "message": f"Docs claim '{claim}' but no corresponding code pattern found",
                        "detail": f"Searched for '{code_pattern}' in all source files",
                    })

    # Deduplicate issues
    seen: set[tuple[str, str]] = set()
    unique_issues: list[dict[str, Any]] = []
    for issue in issues:
        key = (issue["type"], issue["message"])
        if key not in seen:
            seen.add(key)
            unique_issues.append(issue)

    return unique_issues


def _extract_tool_table_names(readme_content: str) -> set[str]:
    """Extract tool names from markdown tables in README."""
    names: set[str] = set()
    for line in readme_content.split("\n"):
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        # Skip header and separator rows
        if "---" in line:
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 2:
            continue
        # Skip the header row (first word "Tool")
        first_word = cells[0].replace("**", "").replace("*", "").strip()
        if first_word.lower() in ("tool", "", "toolcase"):
            continue
        # Extract .py filenames from second (Command) column
        if ".py" in cells[1]:
            m = re.search(r'\*\*([\w.-]+\.py)\*\*', cells[1])
            if m:
                names.add(m.group(1).replace(".py", ""))
            else:
                m = re.search(r'([\w-]+\.py)', cells[1])
                if m:
                    names.add(m.group(1).replace(".py", ""))
        # First column: extract tool filename
        m = re.search(r'\*\*([\w.-]+)\*\*', cells[0])
        if m:
            name = m.group(1).replace(".py", "")
            if name:
                names.add(name.replace(".py", ""))
    return names


# ---------------------------------------------------------------------------
# Report / Output
# ---------------------------------------------------------------------------


def _build_report(
    source_features: dict[str, Any],
    readme_feats: dict[str, Any],
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a structured report."""
    by_severity: dict[str, list[dict[str, Any]]] = {
        "error": [],
        "warning": [],
        "info": [],
    }
    for issue in issues:
        by_severity.setdefault(issue.get("severity", "info"), []).append(issue)

    return {
        "summary": {
            "total": len(issues),
            "errors": len(by_severity.get("error", [])),
            "warnings": len(by_severity.get("warning", [])),
            "info": len(by_severity.get("info", [])),
        },
        "source": {
            "total_tools": len(source_features["tools"]),
            "total_commands": len(source_features["flags"]),
            "has_terminal_endpoint": source_features["has_terminal_endpoint"],
            "has_file_editor": source_features["has_file_editor"],
            "tools": source_features["tools"],
            "flags": source_features["flags"],
        },
        "documentation": {
            "total_tools_mentioned": len(readme_feats["mentioned_tools"]),
            "mentions_terminal": readme_feats["mentions_terminal"],
            "mentions_file_editor": readme_feats["mentions_file_editor"],
            "tools_mentioned": readme_feats["mentioned_tools"],
        },
        "issues": issues,
        "by_severity": by_severity,
    }


def _print_human(report: dict[str, Any]) -> None:
    """Print a human-readable report."""
    s = report["summary"]
    src = report["source"]
    doc = report["documentation"]

    print(f"\n{'='*60}")
    print(f"  📚  Docs Sync Check — Summary")
    print(f"{'='*60}")
    print(f"  Total issues:       {s['total']}")
    print(f"  Errors:             {s['errors']}")
    print(f"  Warnings:           {s['warnings']}")
    print(f"  Info:               {s['info']}")
    print(f"{'─'*60}")
    print(f"  Source:    {src['total_tools']} tools, {src['total_commands']} CLI flags")
    print(f"            terminal endpoint: {'✅' if src['has_terminal_endpoint'] else '❌'}")
    print(f"            file editor:       {'✅' if src['has_file_editor'] else '❌'}")
    print(f"  Docs:      {doc['total_tools_mentioned']} tools mentioned")
    print(f"            terminal claim:   {'✅' if doc['mentions_terminal'] else 'Not claimed'}")
    print(f"            file editor claim:{'✅' if doc['mentions_file_editor'] else 'Not claimed'}")
    print(f"{'='*60}")

    if not s["total"]:
        print(f"\n  ✅  Documentation is in sync with source code!\n")
        return

    # Print issues grouped by severity
    for severity in ("error", "warning", "info"):
        items = report["by_severity"].get(severity, [])
        if not items:
            continue
        icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(severity, "•")
        label = severity.upper()
        print(f"\n  {icon}  {label} ({len(items)}):")
        print(f"  {'─'*56}")
        for issue in items:
            print(f"    [{issue['type']}]")
            print(f"    {issue['message']}")
            if issue.get("detail"):
                print(f"    → {issue['detail']}")
            print()

    print(f"{'─'*60}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether README/docs match the actual code.",
        epilog=(
            "Exit codes: 0 = docs match code, "
            "1 = issues found (out of sync), "
            "2 = error"
        ),
    )
    parser.add_argument(
        "path", nargs="?", default=".",
        help="Project root directory to check (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (machine-readable)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed diagnostic information",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"Error: path does not exist or is not a directory: {root}", file=sys.stderr)
        return 2

    # 1. Find all Python source files
    py_files = collect_python_files(root)
    if not py_files:
        print(f"  ℹ️  No Python source files found in {root}", file=sys.stderr)
        return 0

    # 2. Analyze source code
    source_features = extract_features_from_source(py_files)

    # 3. Read README
    readme_path = root / "README.md"
    if not readme_path.exists():
        readme_path = root / "readme.md"
    if not readme_path.exists():
        # Try alternative locations
        for candidate in root.glob("README*"):
            readme_path = candidate
            break
        else:
            for candidate in root.glob("readme*"):
                readme_path = candidate
                break

    if readme_path.exists():
        readme_content = read_text_file(readme_path)
    else:
        print(f"  ⚠️  No README.md found in {root}", file=sys.stderr)
        print(json.dumps({
            "error": "No README.md found",
            "source_tools": source_features["tools"],
        }) if args.json else "  No README.md to check against code.\n")
        return 1

    # 4. Read docs/ folder
    docs_features = extract_features_from_docs(root / "docs")

    # 5. Compare
    issues = check_docs_sync(root, source_features, readme_content, docs_features)

    # 6. Build report
    readme_feats = extract_features_from_readme(readme_content)
    report = _build_report(source_features, readme_feats, issues)

    if args.verbose:
        report["source"]["files"] = [str(p.relative_to(root)) for p in py_files]
        report["documentation"]["docs_files"] = [
            d.get("file", "") for d in docs_features
        ]

    # 7. Output
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_human(report)

    if issues:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())