#!/usr/bin/env python3
"""
build_doctor.py — Diagnose build and compilation problems.

Detects:
  - npm run build failures
  - vite build errors
  - next build errors
  - tsc --noEmit type errors
  - Python import errors (ModuleNotFoundError, ImportError)
  - Missing dependencies
  - Wrong tsconfig paths / path aliases
  - Wrong alias paths (vite, webpack, jest)
  - Broken package.json scripts
  - Missing npm/pip packages

Usage:
    python build_doctor.py <path>
    python build_doctor.py <path> --json
    python build_doctor.py <path> --fix
"""

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import ast
import json
import re
import shlex
import shutil
from safe_run import SafeRunResult, safe_run
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = frozenset(
    {
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
        ".husky/_",
        ".git2",
        ".svn",
        ".hg",
        "coverage",
        ".nyc_output",
        ".backups",
        ".rsi_backups",
        ".rsi_reports",
        ".self_improve_reports",
    }
)

EXIT_OK = 0
EXIT_ISSUES = 1  # problems found
EXIT_ERROR = 2  # script error

MAX_LINE_LENGTH = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], cwd: Path, timeout: int = 120) -> SafeRunResult:
    """Run a subprocess via safe_run with workspace containment."""
    return safe_run(
        cmd,
        workspace=cwd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        risk_level="medium",
    )


def _which(cmd: str) -> bool:
    """Check if a command is available on PATH."""
    return shutil.which(cmd) is not None


def _safe_read(path: Path) -> str:
    """Read a file safely, returning empty string on error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _glob_scoped(root: Path, pattern: str) -> list[Path]:
    """Glob but skip EXCLUDE_DIRS."""
    results = []
    for p in root.rglob(pattern):
        parts = p.relative_to(root).parts
        if any(excl in parts for excl in EXCLUDE_DIRS):
            continue
        results.append(p)
    return results


# ---------------------------------------------------------------------------
# Check: Node / npm
# ---------------------------------------------------------------------------


def check_npm_build(root: Path) -> list[dict]:
    """Run `npm run build` and capture errors."""
    issues = []
    pkg = root / "package.json"
    if not pkg.exists():
        return []

    if not _which("node"):
        issues.append(
            {
                "severity": "ERROR",
                "type": "npm",
                "check": "npm run build",
                "file": "package.json",
                "message": "Node.js is not installed or not on PATH",
                "cause": "Missing runtime",
                "suggested_fix": "Install Node.js from https://nodejs.org/",
                "retry_command": "winget install OpenJS.NodeJS || nvm install 20",
            }
        )
        return issues

    if not _which("npm"):
        issues.append(
            {
                "severity": "ERROR",
                "type": "npm",
                "check": "npm run build",
                "file": "package.json",
                "message": "npm is not installed or not on PATH",
                "cause": "Missing package manager",
                "suggested_fix": "npm comes with Node.js — reinstall Node.js",
                "retry_command": "winget install OpenJS.NodeJS",
            }
        )
        return issues

    # Check node_modules exists
    nm = root / "node_modules"
    if not nm.exists():
        issues.append(
            {
                "severity": "ERROR",
                "type": "npm",
                "check": "npm run build",
                "file": "package.json",
                "message": "node_modules/ is missing",
                "cause": "Dependencies not installed",
                "suggested_fix": "Run 'npm install' to install dependencies",
                "retry_command": "npm install",
            }
        )
        return issues

    # Check if build script exists in package.json
    try:
        pkg_data = json.loads(_safe_read(pkg))
    except json.JSONDecodeError as e:
        issues.append(
            {
                "severity": "ERROR",
                "type": "npm",
                "check": "npm run build",
                "file": "package.json",
                "message": f"package.json is not valid JSON: {e}",
                "cause": "Malformed package.json",
                "suggested_fix": "Fix the JSON syntax in package.json",
                "retry_command": "",
            }
        )
        return issues

    scripts = pkg_data.get("scripts", {})
    if "build" not in scripts:
        issues.append(
            {
                "severity": "WARN",
                "type": "npm",
                "check": "npm run build",
                "file": "package.json",
                "message": "No 'build' script defined in package.json",
                "cause": "Missing build script",
                "suggested_fix": "Add a 'build' script to package.json (e.g. 'vite build' or 'next build')",
                "retry_command": "",
            }
        )
        return issues

    # Try to run npm run build
    result = _run(["npm", "run", "build"], root, timeout=300)

    if result.returncode == 0:
        return []

    errors = parse_npm_errors(result.stdout + "\n" + result.stderr, root)
    issues.extend(errors)

    # Check for missing dependencies that might cause the build failure
    missing = check_missing_npm_deps(root, pkg_data)
    issues.extend(missing)

    return issues


def parse_npm_errors(output: str, root: Path) -> list[dict]:
    """Parse npm build errors into structured diagnostics."""
    issues = []
    lines = output.split("\n")
    error_lines = [l for l in lines if "error" in l.lower() or "Error" in l]

    # Group errors by file
    file_errors: dict[str, list[str]] = defaultdict(list)
    for line in error_lines:
        # Try to extract file path from error line
        # Pattern: ./src/file.ts:line:col - error ...
        m = re.search(
            r'[`\'"]?((?:\./)?(?:src|app|pages|components|lib|utils|hooks)/[^\s\'":]+)(?:\.\w+)?',
            line,
        )
        if m:
            file_path = m.group(1)
            file_errors[file_path].append(line.strip())
        else:
            file_errors["(general)"].append(line.strip())

    for file_path, errs in file_errors.items():
        issue_type = "npm_build"
        cause = _infer_npm_cause(errs)
        fix = _suggest_npm_fix(cause, errs)
        issues.append(
            {
                "severity": "ERROR",
                "type": issue_type,
                "check": "npm run build",
                "file": file_path,
                "message": errs[0] if errs else "Build failed (see details)",
                "details": errs[:5],
                "cause": cause,
                "suggested_fix": fix,
                "retry_command": f"npm run build 2>&1",
            }
        )

    if not issues:
        issues.append(
            {
                "severity": "ERROR",
                "type": "npm_build",
                "check": "npm run build",
                "file": "(general)",
                "message": "npm run build failed (no parseable errors)",
                "cause": "Unknown build failure",
                "suggested_fix": "Inspect full build output manually",
                "retry_command": "npm run build 2>&1",
            }
        )

    return issues


def check_missing_npm_deps(root: Path, pkg_data: dict) -> list[dict]:
    """Detect missing npm dependencies by reading require/import statements."""
    issues = []
    deps = set(pkg_data.get("dependencies", {}))
    dev_deps = set(pkg_data.get("devDependencies", {}))
    all_deps = deps | dev_deps

    # Scan JS/TS files for imports that aren't in dependencies
    source_files = _glob_scoped(root, "*.{js,jsx,ts,tsx}")
    found_imports: set[str] = set()

    for sf in source_files:
        content = _safe_read(sf)
        # import x from 'pkg' / import 'pkg' / require('pkg')
        for m in re.finditer(
            r"""(?:from\s+['"])([^'"]+)(?:['"])|(?:require\(['"])([^'"]+)(?:['"]\))|(?:import\s+['"])([^'"]+)(?:['"])""",
            content,
        ):
            pkg_name = m.group(1) or m.group(2) or m.group(3)
            if pkg_name and not pkg_name.startswith(".") and not pkg_name.startswith("/"):
                # Get the base package name (handle @scoped/packages)
                parts = pkg_name.split("/")
                if pkg_name.startswith("@"):
                    base = "/".join(parts[:2])
                else:
                    base = parts[0]
                found_imports.add(base)

    missing = found_imports - all_deps
    for pkg in sorted(missing):
        issues.append(
            {
                "severity": "WARN",
                "type": "missing_dep",
                "check": "dependency_check",
                "file": "package.json",
                "message": f"Missing npm dependency: '{pkg}' — imported but not in package.json",
                "cause": "Dependency not declared",
                "suggested_fix": f"Run: npm install {pkg}",
                "retry_command": f"npm install {pkg}",
            }
        )

    return issues


# ---------------------------------------------------------------------------
# Check: vite build
# ---------------------------------------------------------------------------


def check_vite_build(root: Path) -> list[dict]:
    """Run vite build and check for errors."""
    issues = []
    vite_configs = ["vite.config.ts", "vite.config.js", "vite.config.mjs"]
    cfg_file = None

    for cfg in vite_configs:
        if (root / cfg).exists():
            cfg_file = root / cfg
            break

    if cfg_file is None:
        return []

    if not _which("npx") and not _which("vite"):
        issues.append(
            {
                "severity": "ERROR",
                "type": "vite",
                "check": "vite build",
                "file": cfg_file.name,
                "message": "Neither npx nor vite is available on PATH",
                "cause": "Missing runtime",
                "suggested_fix": "Run 'npm install -g vite' or use npx",
                "retry_command": "npx vite build",
            }
        )
        return issues

    # Check if vite is installed in node_modules
    vite_bin = root / "node_modules" / ".bin" / "vite"
    cmd = ["npx", "--yes", "vite", "build"] if not vite_bin.exists() else [str(vite_bin), "build"]
    if _which("vite"):
        cmd = ["vite", "build"]

    result = _run(cmd, root, timeout=300)

    if result.returncode == 0:
        return []

    output = result.stdout + "\n" + result.stderr
    lines = output.split("\n")
    error_lines = [l for l in lines if "error" in l.lower() or "Error" in l or "✘" in l]

    # Parse vite-specific errors
    file_errors: dict[str, list[str]] = defaultdict(list)
    for line in error_lines:
        m = re.search(r"(?:\./)?([^\s:]+\.(?:ts|tsx|js|jsx|vue|svelte)):(\d+):(\d+)", line)
        if m:
            file_errors[m.group(1)].append(line.strip())
        else:
            file_errors["(general)"].append(line.strip())

    for file_path, errs in file_errors.items():
        cause = _infer_vite_cause(errs)
        fix = _suggest_vite_fix(cause, errs)
        issues.append(
            {
                "severity": "ERROR",
                "type": "vite",
                "check": "vite build",
                "file": file_path,
                "message": errs[0] if errs else "vite build failed",
                "details": errs[:5],
                "cause": cause,
                "suggested_fix": fix,
                "retry_command": "npx vite build 2>&1",
            }
        )

    # Check for alias configuration issues
    if cfg_file:
        alias_issues = check_vite_alias_paths(root, cfg_file)
        issues.extend(alias_issues)

    return issues


def check_vite_alias_paths(root: Path, cfg_file: Path) -> list[dict]:
    """Check vite alias paths point to existing directories."""
    issues = []
    content = _safe_read(cfg_file)

    # Find alias patterns: '@': path.resolve(...) or '@' -> 'src' etc.
    alias_pattern = re.compile(
        r"""['"](\@[a-zA-Z0-9_/-]+)['"]\s*[=:]\s*(?:path\.resolve|resolve)\([^)]*['"]([^'"]+)['"]"""
    )
    alias_matches = alias_pattern.findall(content)

    # Also find simple string aliases like '@': 'src'
    simple_alias = re.compile(r"""['"]([^'"]+)['"]\s*[=:]\s*['"]([^'"]+)['"]""")

    # Only capture ones that look like path aliases (start with @ or ~ or are short)
    for m in simple_alias.finditer(content):
        alias = m.group(1)
        target = m.group(2)
        if alias.startswith(("@", "~", "$")) and not target.startswith(("@", "~", "$", "http")):
            alias_matches.append((alias, target))

    for alias, target in alias_matches:
        target_path = root / target
        if not target_path.exists():
            issues.append(
                {
                    "severity": "WARN",
                    "type": "vite_alias",
                    "check": "vite alias paths",
                    "file": cfg_file.name,
                    "message": f"Alias '{alias}' points to '{target}' but that path does not exist",
                    "cause": "Wrong alias configuration",
                    "suggested_fix": f"Update the alias '{alias}' to point to an existing directory, or create '{target}'",
                    "retry_command": "",
                }
            )

    return issues


# ---------------------------------------------------------------------------
# Check: next build
# ---------------------------------------------------------------------------


def check_next_build(root: Path) -> list[dict]:
    """Check Next.js build for errors."""
    issues = []
    next_configs = ["next.config.ts", "next.config.js", "next.config.mjs"]
    cfg_file = None
    for cfg in next_configs:
        if (root / cfg).exists():
            cfg_file = root / cfg
            break

    # Also detect if this is a Next.js project via package.json
    pkg = root / "package.json"
    is_next = cfg_file is not None

    if not is_next and pkg.exists():
        try:
            pkg_data = json.loads(_safe_read(pkg))
            deps_raw = pkg_data.get("dependencies", {})
            deps_dev = pkg_data.get("devDependencies", {})
            deps = list(deps_raw.keys()) + list(deps_dev.keys())
            if any("next" in d for d in deps):
                is_next = True
        except Exception:
            pass

    if not is_next:
        return []

    if not _which("npx") and not _which("next"):
        issues.append(
            {
                "severity": "ERROR",
                "type": "next",
                "check": "next build",
                "file": "next.config.*",
                "message": "next command not found",
                "cause": "Missing runtime",
                "suggested_fix": "Run 'npm install next' or 'npm install'",
                "retry_command": "npm install",
            }
        )
        return issues

    # Check for common Next.js build issues
    # Check pages/app directory
    pages_dir = root / "pages"
    app_dir = root / "app"
    if not pages_dir.exists() and not app_dir.exists():
        issues.append(
            {
                "severity": "ERROR",
                "type": "next",
                "check": "next build",
                "file": "(project root)",
                "message": "Neither 'pages/' nor 'app/' directory found — Next.js has no entry points",
                "cause": "Missing pages or app directory",
                "suggested_fix": "Create pages/ directory with at least an index page",
                "retry_command": "",
            }
        )
        return issues

    cmd = ["npx", "--yes", "next", "build"] if not _which("next") else ["next", "build"]
    result = _run(cmd, root, timeout=300)

    if result.returncode == 0:
        return []

    output = result.stdout + "\n" + result.stderr
    lines = output.split("\n")
    error_lines = [l for l in lines if "error" in l.lower() or "Error" in l]

    file_errors: dict[str, list[str]] = defaultdict(list)
    for line in error_lines:
        m = re.search(r"(?:\./)?([^\s:]+\.(?:ts|tsx|js|jsx))", line)
        if m:
            file_errors[m.group(1)].append(line.strip())
        else:
            file_errors["(general)"].append(line.strip())

    for file_path, errs in file_errors.items():
        cause = _infer_next_cause(errs)
        fix = _suggest_next_fix(cause, errs)
        issues.append(
            {
                "severity": "ERROR",
                "type": "next",
                "check": "next build",
                "file": file_path,
                "message": errs[0] if errs else "next build failed",
                "details": errs[:5],
                "cause": cause,
                "suggested_fix": fix,
                "retry_command": "npx next build 2>&1",
            }
        )

    # Check tsconfig paths used in Next.js
    tsconfig_issues = check_tsconfig_paths(root)
    issues.extend(tsconfig_issues)

    return issues


# ---------------------------------------------------------------------------
# Check: tsc --noEmit
# ---------------------------------------------------------------------------


def check_tsc(root: Path) -> list[dict]:
    """Run `tsc --noEmit` and report type errors."""
    issues = []
    tsconfig = root / "tsconfig.json"
    if not tsconfig.exists():
        return []

    if not _which("npx") and not _which("tsc"):
        issues.append(
            {
                "severity": "ERROR",
                "type": "tsc",
                "check": "tsc --noEmit",
                "file": "tsconfig.json",
                "message": "tsc (TypeScript compiler) not found",
                "cause": "Missing runtime",
                "suggested_fix": "Run 'npm install -g typescript' or 'npm install typescript'",
                "retry_command": "npm install -g typescript",
            }
        )
        return issues

    # Check tsconfig.json is valid
    try:
        tsconfig_data = json.loads(_safe_read(tsconfig))
    except json.JSONDecodeError as e:
        issues.append(
            {
                "severity": "ERROR",
                "type": "tsc",
                "check": "tsc --noEmit",
                "file": "tsconfig.json",
                "message": f"tsconfig.json is not valid JSON: {e}",
                "cause": "Malformed tsconfig.json",
                "suggested_fix": "Fix JSON syntax in tsconfig.json",
                "retry_command": "",
            }
        )
        return issues

    cmd = ["npx", "--yes", "tsc", "--noEmit"] if not _which("tsc") else ["tsc", "--noEmit"]
    result = _run(cmd, root, timeout=180)

    if result.returncode == 0:
        return []

    output = result.stdout + "\n" + result.stderr
    lines = output.split("\n")
    # tsc outputs like: src/index.ts:5:3 - error TS2322: Type 'x' is not assignable
    file_errors: dict[str, list[str]] = defaultdict(list)

    for line in lines:
        m = re.match(
            r"^([^\s:]+\.(?:ts|tsx)):\d+:\d+\s*-\s*(error|warning)\s+(TS\d+):\s*(.*)", line
        )
        if m:
            fpath = m.group(1)
            file_errors[fpath].append(line.strip())

    for file_path, errs in file_errors.items():
        cause = _infer_tsc_cause(errs)
        fix = _suggest_tsc_fix(cause, errs)
        issues.append(
            {
                "severity": "ERROR",
                "type": "tsc",
                "check": "tsc --noEmit",
                "file": file_path,
                "message": errs[0] if errs else "TypeScript type error",
                "details": errs[:10],
                "cause": cause,
                "suggested_fix": fix,
                "retry_command": "npx tsc --noEmit 2>&1",
            }
        )

    if not issues:
        issues.append(
            {
                "severity": "ERROR",
                "type": "tsc",
                "check": "tsc --noEmit",
                "file": "(general)",
                "message": "tsc --noEmit failed with errors (could not parse)",
                "cause": "TypeScript compilation error",
                "suggested_fix": "Run 'npx tsc --noEmit' manually to see full output",
                "retry_command": "npx tsc --noEmit 2>&1",
            }
        )

    # Also check tsconfig paths
    tsconfig_path_issues = check_tsconfig_paths(root)
    issues.extend(tsconfig_path_issues)

    return issues


def check_tsconfig_paths(root: Path) -> list[dict]:
    """Check that paths defined in tsconfig.json compilerOptions.paths exist."""
    issues = []
    tsconfig = root / "tsconfig.json"
    if not tsconfig.exists():
        return []

    try:
        data = json.loads(_safe_read(tsconfig))
    except Exception:
        return []

    paths = data.get("compilerOptions", {}).get("paths", {})
    if not paths:
        return []

    for alias, targets in paths.items():
        for target in targets:
            # ts paths like "@/*": ["src/*"]  →  check src/ exists
            # Remove wildcards
            clean_target = target.replace("*", "").rstrip("/")
            if not clean_target:
                clean_target = target

            target_path = root / clean_target
            if not target_path.exists():
                issues.append(
                    {
                        "severity": "WARN",
                        "type": "tsconfig_path",
                        "check": "tsconfig paths",
                        "file": "tsconfig.json",
                        "message": f"Path alias '{alias}' → '{target}' points to non-existent location '{clean_target}'",
                        "cause": "Wrong tsconfig path configuration",
                        "suggested_fix": f"Update path '{clean_target}' to an existing directory, or create it",
                        "retry_command": "",
                    }
                )

    # Also check baseUrl if set
    base_url = data.get("compilerOptions", {}).get("baseUrl", "")
    if base_url:
        base_path = root / base_url
        if not base_path.exists():
            issues.append(
                {
                    "severity": "WARN",
                    "type": "tsconfig_path",
                    "check": "tsconfig paths",
                    "file": "tsconfig.json",
                    "message": f"baseUrl '{base_url}' points to non-existent location",
                    "cause": "Wrong baseUrl in tsconfig",
                    "suggested_fix": f"Set baseUrl to an existing directory (e.g. '.') or create '{base_url}'",
                    "retry_command": "",
                }
            )

    return issues


# ---------------------------------------------------------------------------
# Check: Python import errors
# ---------------------------------------------------------------------------


def check_python_imports(root: Path) -> list[dict]:
    """Scan Python files for import errors without full execution."""
    issues = []
    py_files = _glob_scoped(root, "*.py")

    if not py_files:
        return []

    # Check Python availability
    python_cmd = None
    for candidate in ["python3", "python"]:
        if _which(candidate):
            python_cmd = candidate
            break

    if not python_cmd:
        issues.append(
            {
                "severity": "ERROR",
                "type": "python",
                "check": "Python import check",
                "file": "(global)",
                "message": "Python interpreter not found on PATH",
                "cause": "Missing runtime",
                "suggested_fix": "Install Python from python.org or your package manager",
                "retry_command": "winget install Python.Python.3.11",
            }
        )
        return issues

    # Try to parse each Python file with ast to check syntax (no .pyc written)
    for py_file in py_files:
        try:
            source = _safe_read(py_file)
            ast.parse(source, filename=str(py_file))
        except SyntaxError as e:
            issues.append(
                {
                    "severity": "ERROR",
                    "type": "python",
                    "check": "Python syntax",
                    "file": str(py_file.relative_to(root)),
                    "message": f"Syntax error: {e.msg} (line {e.lineno})",
                    "cause": "Python syntax error",
                    "suggested_fix": f"Fix syntax in {py_file.name}",
                    "retry_command": f'{python_cmd} -m py_compile "{py_file}"',
                }
            )
        except PermissionError:
            issues.append(
                {
                    "severity": "WARN",
                    "type": "python",
                    "check": "Python syntax",
                    "file": str(py_file.relative_to(root)),
                    "message": "Could not check syntax: file not readable (permissions)",
                    "cause": "Permission denied",
                    "suggested_fix": "Check file permissions",
                    "retry_command": "",
                }
            )
        except Exception as e:
            issues.append(
                {
                    "severity": "WARN",
                    "type": "python",
                    "check": "Python syntax",
                    "file": str(py_file.relative_to(root)),
                    "message": f"Could not check syntax: {e}",
                    "cause": "Unexpected error",
                    "suggested_fix": "Check file manually",
                    "retry_command": "",
                }
            )

    # Check for missing imports by scanning import statements
    import_issues = check_missing_python_imports(root, py_files)
    issues.extend(import_issues)

    return issues


def check_missing_python_imports(root: Path, py_files: list[Path]) -> list[dict]:
    """Check for imported modules that might be missing."""
    issues = []
    # Use Python's own stdlib list (3.10+) with fallback for older versions
    try:
        stdlib_modules = set(sys.stdlib_module_names)
    except AttributeError:
        stdlib_modules = {
            "os",
            "sys",
            "re",
            "json",
            "math",
            "time",
            "datetime",
            "pathlib",
            "collections",
            "functools",
            "itertools",
            "typing",
            "abc",
            "enum",
            "hashlib",
            "random",
            "string",
            "textwrap",
            "uuid",
            "copy",
            "dis",
            "inspect",
            "pprint",
            "argparse",
            "logging",
            "subprocess",
            "shutil",
            "tempfile",
            "io",
            "base64",
            "binascii",
            "struct",
            "pickle",
            "shelve",
            "sqlite3",
            "csv",
            "configparser",
            "xml",
            "html",
            "http",
            "urllib",
            "socket",
            "ssl",
            "email",
            "statistics",
            "decimal",
            "fractions",
            "unittest",
            "doctest",
            "dataclasses",
            "importlib",
            "ast",
            "keyword",
            "tokenize",
            "traceback",
            "warnings",
            "weakref",
            "threading",
            "multiprocessing",
            "asyncio",
            "concurrent",
            "difflib",
            "webbrowser",
            "filecmp",
            "stat",
            "glob",
            "fnmatch",
            "pathlib",
            "atexit",
            "signal",
            "mmap",
            "ctypes",
            "platform",
            "getpass",
            "calendar",
            "locale",
            "gettext",
            "textwrap",
            "pprint",
            "reprlib",
            "array",
            "bisect",
            "heapq",
            "operator",
            "functools",
            "itertools",
        }

    # Get installed packages
    installed = set()
    for cmd in ["python3", "python"]:
        if _which(cmd):
            try:
                result = _run([cmd, "-m", "pip", "list", "--format=freeze"], root)
                for line in result.stdout.strip().split("\n"):
                    if "==" in line:
                        installed.add(line.split("==")[0].lower())
            except Exception:
                pass
            break

    # Scan each file for imports and check if they're available
    for py_file in py_files:
        content = _safe_read(py_file)
        rel = str(py_file.relative_to(root))

        # Find all imports
        import_patterns = [
            r"^import\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)",
            r"^from\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\s+import",
        ]

        for pattern in import_patterns:
            for m in re.finditer(pattern, content, re.MULTILINE):
                mod = m.group(1).split(".")[0]
                if mod in stdlib_modules:
                    continue
                # Check if it's a local module
                local_module = py_file.parent / f"{mod}.py"
                local_package = py_file.parent / mod / "__init__.py"
                if local_module.exists() or local_package.exists():
                    continue
                # Check relative imports within project
                if mod not in installed and mod not in ["__future__"]:
                    # Might be a local module in a different directory
                    # Try broader search
                    found = False
                    for candidate in py_files:
                        if candidate.stem == mod:
                            found = True
                            break
                    if not found:
                        issues.append(
                            {
                                "severity": "WARN",
                                "type": "python_import",
                                "check": "Python imports",
                                "file": rel,
                                "message": f"'{mod}' is imported but may not be installed (not found in pip list or local files)",
                                "cause": "Missing Python dependency",
                                "suggested_fix": f"Run: pip install {mod}",
                                "retry_command": f"pip install {mod}",
                            }
                        )

    return issues


# ---------------------------------------------------------------------------
# Check: package.json scripts
# ---------------------------------------------------------------------------


def check_package_scripts(root: Path) -> list[dict]:
    """Check that package.json scripts reference valid commands."""
    issues = []
    pkg = root / "package.json"
    if not pkg.exists():
        return []

    try:
        pkg_data = json.loads(_safe_read(pkg))
    except Exception:
        return []

    scripts = pkg_data.get("scripts", {})
    if not scripts:
        return []

    for name, script in scripts.items():
        # Check for broken reference patterns
        # e.g. "build": "vite build" — but vite isn't installed
        if not script.strip():
            issues.append(
                {
                    "severity": "WARN",
                    "type": "broken_script",
                    "check": "package.json scripts",
                    "file": "package.json",
                    "message": f"Script '{name}' is empty",
                    "cause": "Empty script definition",
                    "suggested_fix": f"Remove or implement the '{name}' script",
                    "retry_command": "",
                }
            )
            continue

        # Extract the first command (before pipes, &&, etc.)
        first_cmd = script.strip().split("&&")[0].split("|")[0].strip()
        first_word = first_cmd.split()[0] if first_cmd.split() else ""

        # Skip npx prefix
        if first_word == "npx":
            first_word = first_cmd.split()[1] if len(first_cmd.split()) > 1 else ""

        # Known valid commands that come from packages
        known_binaries = {
            "vite",
            "tsc",
            "next",
            "eslint",
            "prettier",
            "jest",
            "vitest",
            "webpack",
            "rollup",
            "postcss",
            "tailwindcss",
            "sass",
            "less",
            "babel",
            "terser",
            "swc",
            "tsup",
            "esbuild",
            "nodemon",
            "concurrently",
            "cross-env",
            "rimraf",
            "mkdirp",
            "cpy-cli",
            "npm",
            "node",
            "yarn",
            "pnpm",
        }

        if first_word in known_binaries:
            continue

        # Check if the command exists as a binary in node_modules/.bin
        bin_path = root / "node_modules" / ".bin" / first_word
        if first_word and bin_path.exists():
            continue

        # It might be a reference to another script via npm run
        if first_word in scripts:
            continue

        # If it's a relative path to a script
        if first_word.startswith("./") or first_word.startswith(".\\"):
            script_path = root / first_word
            if not script_path.exists():
                issues.append(
                    {
                        "severity": "WARN",
                        "type": "broken_script",
                        "check": "package.json scripts",
                        "file": "package.json",
                        "message": f"Script '{name}' references '{first_word}' which doesn't exist",
                        "cause": "File not found for script execution",
                        "suggested_fix": f"Create the script file at '{first_word}' or fix the path",
                        "retry_command": "",
                    }
                )
            continue

        # Otherwise it might be a custom script in project
        # Check if there's a matching file
        script_file = root / f"{first_word}.js"
        if first_word and not script_file.exists() and first_word not in known_binaries:
            issues.append(
                {
                    "severity": "INFO",
                    "type": "broken_script",
                    "check": "package.json scripts",
                    "file": "package.json",
                    "message": (
                        "Script '{name}' = '{script}' — command"
                        "'{first_word}' is not a known binary, may be missing"
                    ),
                    "cause": "Potentially unknown script command",
                    "suggested_fix": f"Ensure '{first_word}' is installed or define it as a project script",
                    "retry_command": "",
                }
            )

    return issues


# ---------------------------------------------------------------------------
# Check: missing dependencies (comprehensive)
# ---------------------------------------------------------------------------


def check_missing_deps(root: Path) -> list[dict]:
    """Comprehensive dependency check across all project types."""
    issues = []

    # Check package.json deps vs node_modules
    pkg = root / "package.json"
    if pkg.exists():
        try:
            pkg_data = json.loads(_safe_read(pkg))
            all_deps = {}
            all_deps.update(pkg_data.get("dependencies", {}))
            all_deps.update(pkg_data.get("devDependencies", {}))
            all_deps.update(pkg_data.get("peerDependencies", {}))

            nm = root / "node_modules"
            if nm.exists():
                for dep_name in all_deps:
                    dep_path = nm / dep_name
                    # Handle scoped packages (@scope/name)
                    if dep_name.startswith("@") and "/" in dep_name:
                        dep_path = nm / dep_name.replace("/", "\\")
                    # Check on both OS path styles
                    dep_path_alt = nm / dep_name
                    if not dep_path.exists() and not dep_path_alt.exists():
                        issues.append(
                            {
                                "severity": "ERROR",
                                "type": "missing_dep",
                                "check": "dependencies",
                                "file": "package.json",
                                "message": f"Missing npm package: '{dep_name}' (declared but not installed in node_modules)",
                                "cause": "Dependency not installed",
                                "suggested_fix": f"Run: npm install {dep_name}",
                                "retry_command": f"npm install {dep_name}",
                            }
                        )
        except Exception:
            pass

    # Check requirements.txt / pyproject.toml
    req_file = root / "requirements.txt"
    if req_file.exists():
        try:
            content = _safe_read(req_file)
            for line in content.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "==" in line:
                    pkg_name = line.split("==")[0].strip()
                elif ">=" in line:
                    pkg_name = line.split(">=")[0].strip()
                else:
                    pkg_name = line
                if pkg_name:
                    try:
                        result = _run(
                            [
                                python_cmd := "python3" if _which("python3") else "python",
                                "-c",
                                f"import {pkg_name.replace('-', '_')}",
                            ],
                            root,
                        )
                        if result.returncode != 0:
                            # Try with dashes replaced
                            pass
                    except Exception:
                        issues.append(
                            {
                                "severity": "WARN",
                                "type": "missing_dep",
                                "check": "dependencies",
                                "file": "requirements.txt",
                                "message": f"Missing Python package: '{pkg_name}' (declared but may not be installed)",
                                "cause": "Python dependency not installed",
                                "suggested_fix": f"Run: pip install {pkg_name}",
                                "retry_command": f"pip install {pkg_name}",
                            }
                        )
        except Exception:
            pass

    return issues


# ---------------------------------------------------------------------------
# Cause inference helpers
# ---------------------------------------------------------------------------


def _infer_npm_cause(errors: list[str]) -> str:
    """Infer the most likely cause of npm build errors."""
    combined = " ".join(errors).lower()
    if "module not found" in combined or "cannot find module" in combined:
        return "Missing or misnamed module import"
    if "syntaxerror" in combined or "unexpected token" in combined:
        return "JavaScript/TypeScript syntax error"
    if "ts2307" in combined:
        return "TypeScript cannot find module (wrong import path)"
    if "ts2322" in combined:
        return "TypeScript type mismatch"
    if "ts2345" in combined:
        return "TypeScript argument type mismatch"
    if "ts2339" in combined:
        return "Property does not exist on type"
    if "ts2769" in combined:
        return "No overload matches this call"
    if "ts2554" in combined:
        return "Wrong number of arguments"
    if "ts18047" in combined:
        return "Object is possibly 'null' or 'undefined'"
    if "ts18046" in combined:
        return "'{}' is of type 'unknown'"
    if "ts7006" in combined:
        return "Parameter implicitly has 'any' type"
    if "ts7031" in combined:
        return "Binding element implicitly has 'any' type"
    if "ts2741" in combined:
        return "Missing property in object literal"
    if "eslint" in combined:
        return "ESLint error during build"
    if "resolve" in combined and "alias" in combined:
        return "Path alias resolution failure"
    if "postcss" in combined:
        return "PostCSS configuration error"
    if "sass" in combined or "scss" in combined:
        return "SASS/SCSS compilation error"
    return "General build error (see details)"


def _suggest_npm_fix(cause: str, errors: list[str]) -> str:
    """Suggest a fix based on the inferred cause."""
    combined = " ".join(errors).lower()

    if "module not found" in combined or "cannot find module" in combined:
        # Try to extract the module name
        m = re.search(r"['\"]((?:@[^'\"]+/)?[^'\"\\/]+)['\"]", combined)
        mod_name = m.group(1) if m else "<module>"
        return f"Install the missing module: 'npm install {mod_name}' or fix the import path"
    if "syntaxerror" in combined or "unexpected token" in combined:
        return "Check for syntax errors (missing brackets, commas, etc.)"
    if "ts2307" in combined:
        return "Check the import path — the module may be misnamed or in a different location"
    if "ts2322" in combined:
        return "Check the type definition — ensure the variable can accept the assigned type"
    if "ts2345" in combined:
        return "Check function signature — the argument type doesn't match the parameter type"
    if "ts2339" in combined:
        return "Check the property name — it may be misspelled or not exist on that type"
    if "ts2769" in combined:
        return "Check the function call — no overload accepts these argument types"
    if "alias" in combined:
        return (
            "Check vite/tsconfig alias configuration — the alias may point to a non-existent path"
        )
    return "Inspect the error output above and fix accordingly"


def _infer_vite_cause(errors: list[str]) -> str:
    """Infer cause of vite build errors."""
    combined = " ".join(errors).lower()
    if "failed to resolve" in combined or "cannot find module" in combined:
        return "Vite cannot resolve an import — missing module or wrong path"
    if "syntaxerror" in combined:
        return "Syntax error in source file"
    if "plugin" in combined and "error" in combined:
        return "Vite plugin error"
    if "css" in combined:
        return "CSS/PostCSS processing error"
    return _infer_npm_cause(errors)


def _suggest_vite_fix(cause: str, errors: list[str]) -> str:
    """Suggest fix for vite build errors."""
    combined = " ".join(errors).lower()
    if "resolve" in combined:
        return "Check import paths — use relative paths or configure aliases in vite.config.*"
    return _suggest_npm_fix(cause, errors)


def _infer_next_cause(errors: list[str]) -> str:
    """Infer cause of next build errors."""
    combined = " ".join(errors).lower()
    if "module not found" in combined or "cannot find module" in combined:
        return "Missing module import"
    if "hydration" in combined:
        return "React hydration mismatch between server and client"
    if "getserversideprops" in combined or "getstaticprops" in combined:
        return "Error in data fetching method (getServerSideProps/getStaticProps)"
    if "404" in combined or "not found" in combined:
        return "Page or API route not found"
    if "image" in combined and "optimization" in combined:
        return "Next.js image optimization error"
    if "middleware" in combined:
        return "Next.js middleware error"
    return _infer_npm_cause(errors)


def _suggest_next_fix(cause: str, errors: list[str]) -> str:
    """Suggest fix for next build errors."""
    combined = " ".join(errors).lower()
    if "hydration" in combined:
        return "Ensure server and client render the same HTML — check for browser-only APIs in SSR"
    if "module" in combined:
        return "Check import paths and ensure all dependencies are installed"
    return _suggest_npm_fix(cause, errors)


def _infer_tsc_cause(errors: list[str]) -> str:
    """Infer cause of TypeScript errors."""
    combined = " ".join(errors).lower()
    if "ts2307" in combined:
        return "Cannot find module — wrong import path"
    if "ts2322" in combined:
        return "Type mismatch — incompatible types"
    if "ts2339" in combined:
        return "Property does not exist on the given type"
    if "ts2345" in combined:
        return "Argument type does not match parameter type"
    if "ts2554" in combined:
        return "Incorrect number of function arguments"
    if "ts2741" in combined:
        return "Missing required property in object literal"
    if "ts2769" in combined:
        return "No overload matches this call"
    if "ts18047" in combined:
        return "Object is possibly null/undefined — needs null check"
    if "ts7016" in combined:
        return "Could not find type declaration file for module"
    return "TypeScript compilation error"


def _suggest_tsc_fix(cause: str, errors: list[str]) -> str:
    """Suggest fix for tsc errors."""
    if "ts7016" in cause or "ts7016" in " ".join(errors):
        return "Install type declarations: 'npm install @types/<package>' or add 'declare module'"
    if "null" in cause.lower() or "undefined" in cause.lower():
        return "Add null/undefined checks (optional chaining, default values, or type guards)"
    if "overload" in cause.lower():
        return "Check function arguments — the call doesn't match any available overload"
    return (
        _suggest_npm_fix(cause, errors)
        if "module" in cause.lower()
        else "Fix the type according to the error message above"
    )


# ---------------------------------------------------------------------------
# Master check dispatcher
# ---------------------------------------------------------------------------


def run_all_checks(root: Path) -> list[dict]:
    """Run all applicable build checks."""
    all_issues = []

    checks = [
        ("npm run build", check_npm_build),
        ("vite build", check_vite_build),
        ("next build", check_next_build),
        ("tsc --noEmit", check_tsc),
        ("Python imports", check_python_imports),
        ("package scripts", check_package_scripts),
        ("missing dependencies", check_missing_deps),
    ]

    for check_name, check_fn in checks:
        try:
            result = check_fn(root)
            all_issues.extend(result)
        except Exception as e:
            all_issues.append(
                {
                    "severity": "ERROR",
                    "type": "internal",
                    "check": check_name,
                    "file": "(internal)",
                    "message": f"Check '{check_name}' failed with exception: {e}",
                    "cause": "Internal error in build_doctor",
                    "suggested_fix": "Report this as a bug",
                    "retry_command": "",
                }
            )

    return all_issues


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(all_issues: list[dict]) -> None:
    """Print a formatted build diagnostics report."""
    if not all_issues:
        print(f"\n{'=' * 60}")
        print(f" ✅ BUILD DOCTOR — No issues found!")
        print(f"{'=' * 60}")
        print()
        return

    by_check = defaultdict(list)
    for issue in all_issues:
        by_check[issue["type"]].append(issue)

    errors = [i for i in all_issues if i["severity"] == "ERROR"]
    warnings = [i for i in all_issues if i["severity"] == "WARN"]
    infos = [i for i in all_issues if i["severity"] == "INFO"]

    print(f"\n{'=' * 60}")
    print(f" 🔧 BUILD DOCTOR — {len(all_issues)} issue(s) found")
    print(f"{'=' * 60}")
    print(f"   ❌ Errors:   {len(errors)}")
    print(f"   ⚠  Warnings: {len(warnings)}")
    print(f"   💡 Info:     {len(infos)}")
    print()

    type_names = {
        "npm": "npm Build",
        "npm_build": "npm Build",
        "vite": "Vite Build",
        "vite_alias": "Vite Aliases",
        "next": "Next.js Build",
        "tsc": "TypeScript Compiler",
        "tsconfig_path": "tsconfig Paths",
        "python": "Python",
        "python_import": "Python Imports",
        "broken_script": "Package Scripts",
        "missing_dep": "Missing Dependencies",
        "internal": "Internal Errors",
    }

    for type_key, issues in sorted(by_check.items()):
        type_name = type_names.get(type_key, type_key)
        print(f" ── {type_name} ({len(issues)}) ──")

        for issue in issues:
            icon = (
                "❌"
                if issue["severity"] == "ERROR"
                else ("⚠" if issue["severity"] == "WARN" else "ℹ")
            )
            print(f"   {icon} [{issue.get('file', '?')}] {issue['message']}")
            if issue.get("cause"):
                print(f"      🔍 Cause: {issue['cause']}")
            if issue.get("suggested_fix"):
                print(f"      🔧 Fix: {issue['suggested_fix']}")
            if issue.get("retry_command"):
                print(f"      ▶  Retry: {issue['retry_command']}")
            if issue.get("details"):
                for d in issue["details"][:3]:
                    print(f"         {d}")
            print()

    # Summary: most likely cause
    print(f" ── Summary ──")
    if errors:
        cause_counts: dict[str, int] = defaultdict(int)
        for i in errors:
            cause_counts[i.get("cause", "Unknown")] += 1
        top_cause = max(cause_counts, key=cause_counts.get)
        print(f"   Most likely root cause: {top_cause}")
        print(
            f"   Recommended first action: "
            f"{errors[0].get('suggested_fix', 'Check the errors above')}"
        )
    print()


def build_json_output(all_issues: list[dict]) -> dict:
    """Build JSON output structure."""
    errors = [i for i in all_issues if i["severity"] == "ERROR"]
    warnings = [i for i in all_issues if i["severity"] == "WARN"]
    infos = [i for i in all_issues if i["severity"] == "INFO"]

    # Group by file
    by_file = defaultdict(list)
    for issue in all_issues:
        file_key = issue.get("file", "(unknown)")
        by_file[file_key].append(issue)

    # Most likely cause
    cause_counts: dict[str, int] = defaultdict(int)
    for i in errors:
        cause_counts[i.get("cause", "Unknown")] += 1
    most_likely_cause = max(cause_counts, key=cause_counts.get) if cause_counts else "No errors"

    return {
        "total": len(all_issues),
        "errors": len(errors),
        "warnings": len(warnings),
        "infos": len(infos),
        "most_likely_cause": most_likely_cause,
        "issues_by_file": {k: v for k, v in sorted(by_file.items())},
        "issues": all_issues,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """main."""
    parser = argparse.ArgumentParser(
        description="build_doctor.py — Diagnose build and compilation problems",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python build_doctor.py .
  python build_doctor.py src/ --json
  python build_doctor.py . --fix
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root directory to diagnose")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--fix",
        "-f",
        action="store_true",
        help="Attempt auto-fixes (install missing deps where possible)",
    )
    parser.add_argument(
        "--checks",
        "-c",
        nargs="+",
        choices=["npm", "vite", "next", "tsc", "python", "scripts", "deps"],
        help="Run specific checks only",
    )
    parser.add_argument("--version", action="version", version="build_doctor.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' does not exist", file=sys.stderr)
        sys.exit(EXIT_ERROR)

    if not target.is_dir():
        print(f" ❌ '{args.path}' is not a directory", file=sys.stderr)
        sys.exit(EXIT_ERROR)

    print(f"\n🔧 Build Doctor v1.0.0 — diagnosing {target}")
    print(f"   Scanning for build configs and running diagnostics...\n")

    # Map check names to functions
    check_map = {
        "npm": check_npm_build,
        "vite": check_vite_build,
        "next": check_next_build,
        "tsc": check_tsc,
        "python": check_python_imports,
        "scripts": check_package_scripts,
        "deps": check_missing_deps,
    }

    if args.checks:
        # Run specific checks
        all_issues = []
        for check_name in args.checks:
            fn = check_map[check_name]
            try:
                result = fn(target)
                all_issues.extend(result)
            except Exception as e:
                all_issues.append(
                    {
                        "severity": "ERROR",
                        "type": "internal",
                        "check": check_name,
                        "file": "(internal)",
                        "message": f"Check '{check_name}' failed: {e}",
                        "cause": "Internal error",
                        "suggested_fix": "Report as bug",
                        "retry_command": "",
                    }
                )
    else:
        all_issues = run_all_checks(target)

    # Sort issues: errors first, then warnings, then infos
    severity_order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    all_issues.sort(key=lambda x: (severity_order.get(x["severity"], 99), x.get("file", "")))

    # Auto-fix if requested (limited to installable deps)
    fixed = []
    if args.fix:
        for issue in all_issues:
            retry = issue.get("retry_command", "")
            if retry and issue["severity"] == "ERROR" and issue["type"] == "missing_dep":
                try:
                    args_list = shlex.split(retry)
                    safe_run(
                        args_list, workspace=target, cwd=str(target),
                        capture_output=True, text=True, timeout=60
                    )
                    fixed.append(f"Ran: {retry}")
                except Exception as e:
                    fixed.append(f"Failed: {retry} — {e}")

    if args.json:
        output = build_json_output(all_issues)
        if fixed:
            output["auto_fixed"] = fixed
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print_report(all_issues)
        if fixed:
            print(f" ── Auto-fixes ({len(fixed)}) ──")
            for f in fixed:
                print(f"   {f}")
            print()

    if any(i["severity"] == "ERROR" for i in all_issues):
        sys.exit(EXIT_ISSUES)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
