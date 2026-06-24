#!/usr/bin/env python3
"""
project_doctor.py — Diagnose project health and structural issues.

Checks:
  - Project structure completeness (src/, tests/, docs/, configs)
  - Missing __init__.py files in Python packages
  - Broken symbolic links
  - Orphaned files (_.bak, _.pyc, etc.)
  - Empty directories
  - Inconsistent naming conventions
  - Git status: uncommitted changes, detached HEAD, branch info
  - Large files that shouldn't be committed

Gebruik:
    python project_doctor.py <path>
    python project_doctor.py <path> --fix
    python project_doctor.py <path> --json
    python project_doctor.py <path> --deep
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

# Ensure UTF-8 output on all platforms (Windows cp1252 can't handle emoji/unicode)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = frozenset({
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    ".tox", ".eggs", "build", "dist", ".next", ".husky/_",
    ".git2", ".svn", ".hg", ".backups", ".self_improve_reports",
    ".rsi_reports", ".rsi_backups", ".pytest_cache", ".cache",
})

PYTHON_PACKAGE_MARKERS = {"__init__.py", "__init__.pyi"}
ORPHANED_EXTENSIONS = {".bak", ".pyc", ".pyo", ".orig", ".rej", ".swp", ".swo"}
LARGE_FILE_THRESHOLD = 500 * 1024  # 500 KB
MAX_FILE_SIZE_WARN = 10 * 1024 * 1024  # 10 MB

EXPECTED_DIRS = {
    "src": "Source code",
    "tests": "Test suite",
    "docs": "Documentation",
    "scripts": "Utility scripts",
    "config": "Configuration files",
    "assets": "Static assets (images, fonts, etc.)",
}

EXPECTED_FILES = {
    ".gitignore": "Git ignore rules",
    "README.md": "Project description",
    "LICENSE": "License file",
}

NAMED_CONVENTIONS = {
    "python": {
        "pattern": re.compile(r'^[a-z][a-z0-9_]*\.py$'),
        "desc": "snake_case",
    },
    "typescript": {
        "pattern": re.compile(r'^[A-Z][A-Za-z0-9]*\.tsx?$|^[a-z][a-z0-9-]*\.tsx?$'),
        "desc": "PascalCase (components) or kebab-case (utilities)",
    },
    "rust": {
        "pattern": re.compile(r'^[a-z][a-z0-9_]*\.rs$'),
        "desc": "snake_case",
    },
}


def diagnose_structure(root: Path) -> list[dict]:
    """Check project directory structure."""
    issues = []

    has_src = (root / "src").exists()
    has_tests = (root / "tests").exists()

    if has_src and not has_tests:
        issues.append({
            "severity": "WARN",
            "type": "structure",
            "message": "Tests map ontbreekt (src/ bestaat wel, tests/ niet)",
            "fix": "mkdir tests",
        })

    has_flat_sources = any(
        path.name != "__init__.py" and not path.name.startswith("test_")
        for path in root.glob("*.py")
    )
    if has_tests and not has_src and not has_flat_sources:
        issues.append({
            "severity": "INFO",
            "type": "structure",
            "message": "Source map ontbreekt (tests/ bestaat, src/ niet)",
            "fix": "mkdir src",
        })

    if not (root / "docs").exists():
        issues.append({
            "severity": "INFO",
            "type": "structure",
            "message": "Documentatie map (docs/) ontbreekt",
            "fix": "mkdir docs",
        })

    return issues


def find_missing_init_files(root: Path) -> list[dict]:
    """Find Python directories without __init__.py."""
    issues = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        path = Path(dirpath)

        has_py = any(f.endswith(".py") for f in filenames)
        has_init = any(f in PYTHON_PACKAGE_MARKERS for f in filenames)

        if has_py and not has_init:
            # Check if this is a namespace package (PEP 420)
            rel = path.relative_to(root)
            issues.append({
                "severity": "WARN",
                "type": "init",
                "message": f"Geen __init__.py in Python directory: {rel}",
                "fix": f"touch {rel / '__init__.py'}",
            })

    return issues


def find_orphaned_files(root: Path) -> list[dict]:
    """Find orphaned/leftover files."""
    issues = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            ext = Path(fn).suffix.lower()
            if ext in ORPHANED_EXTENSIONS:
                fp = Path(dirpath) / fn
                issues.append({
                    "severity": "INFO",
                    "type": "orphaned",
                    "message": f"Orphaned file: {fp.relative_to(root)}",
                    "fix": f"rm '{fp}'",
                })

    return issues


def find_empty_dirs(root: Path) -> list[dict]:
    """Find empty directories."""
    issues = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        path = Path(dirpath)

        if not filenames and not dirnames:
            rel = path.relative_to(root)
            if str(rel) != ".":
                issues.append({
                    "severity": "INFO",
                    "type": "empty_dir",
                    "message": f"Lege directory: {rel}",
                    "fix": f"rmdir '{path}'  # of voeg bestanden toe",
                })

    return issues


def find_large_files(root: Path) -> list[dict]:
    """Find files that are too large for version control."""
    issues = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            try:
                fp = Path(dirpath) / fn
                size = fp.stat().st_size
                if size > MAX_FILE_SIZE_WARN:
                    ext = fp.suffix.lower()
                    binary_exts = {".png", ".jpg", ".jpeg", ".gif", ".mp3", ".mp4",
                                   ".zip", ".tar", ".gz", ".7z", ".pdf", ".exe", ".dll"}
                    if ext not in binary_exts:
                        issues.append({
                            "severity": "WARN",
                            "type": "large_file",
                            "message": f"Groot bestand ({size // 1024} KB): {fp.relative_to(root)}",
                            "fix": "Overweeg .gitignore of git LFS",
                        })
                elif size > LARGE_FILE_THRESHOLD:
                    ext = fp.suffix.lower()
                    binary_exts = {".png", ".jpg", ".jpeg", ".gif", ".mp3", ".mp4",
                                   ".zip", ".tar", ".gz", ".7z", ".pdf"}
                    if ext not in binary_exts:
                        issues.append({
                            "severity": "INFO",
                            "type": "large_file",
                            "message": f"Vrij groot bestand ({size // 1024} KB): {fp.relative_to(root)}",
                            "fix": "Overweeg of dit bestand zo groot moet zijn",
                        })
            except Exception:
                continue

    return issues


def check_naming_conventions(root: Path) -> list[dict]:
    """Check file naming conventions per language."""
    issues = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            ext = Path(fn).suffix.lower()

            if ext == ".py":
                convention = NAMED_CONVENTIONS["python"]
            elif ext in (".ts", ".tsx"):
                convention = NAMED_CONVENTIONS["typescript"]
            elif ext == ".rs":
                convention = NAMED_CONVENTIONS["rust"]
            else:
                continue

            if not convention["pattern"].match(fn):
                fp = Path(dirpath) / fn
                issues.append({
                    "severity": "INFO",
                    "type": "naming",
                    "message": f"Naamgeving mogelijk inconsistent: {fp.relative_to(root)}",
                    "detail": f"Verwacht: {convention['desc']}",
                    "fix": f"Hernoem volgens {convention['desc']}",
                })

    return issues


def check_git_status(root: Path) -> list[dict]:
    """Check git repository status."""
    issues = []
    git_dir = root / ".git"

    if not git_dir.exists():
        issues.append({
            "severity": "WARN",
            "type": "git",
            "message": "Geen git repository — niet versiebeheerd",
            "fix": "git init  # of git clone",
        })
        return issues

    try:
        import subprocess
        # Check branch
        result = subprocess.run(
            ["git", "-C", str(root), "branch", "--show-current"],
            capture_output=True, text=True, timeout=10
        )
        branch = result.stdout.strip()
        if branch:
            issues.append({
                "severity": "INFO",
                "type": "git",
                "message": f"Huidige branch: {branch}",
                "detail": "Git repo is actief",
            })
        else:
            # Detached HEAD
            result = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=10
            )
            sha = result.stdout.strip()
            issues.append({
                "severity": "WARN",
                "type": "git",
                "message": f"Detached HEAD op {sha} — niet op een branch",
                "fix": "git checkout <branch>  # of git switch -c <nieuwe-branch>",
            })

        # Check uncommitted changes
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10
        )
        uncommitted = [l for l in result.stdout.split("\n") if l.strip()]
        if uncommitted:
            issues.append({
                "severity": "INFO",
                "type": "git",
                "message": f"{len(uncommitted)} uncommitted change(s)",
                "fix": "git add . && git commit  # of git stash",
            })

        # Check unpushed commits
        result = subprocess.run(
            ["git", "-C", str(root), "log", "--oneline", "@{u}..HEAD", "--"],
            capture_output=True, text=True, timeout=10
        )
        unpushed = [l for l in result.stdout.split("\n") if l.strip()]
        if unpushed:
            issues.append({
                "severity": "INFO",
                "type": "git",
                "message": f"{len(unpushed)} unpushed commit(s)",
                "fix": "git push",
            })

    except Exception as e:
        issues.append({
            "severity": "INFO",
            "type": "git",
            "message": f"Git check mislukt: {e}",
        })

    return issues


def check_project_files(root: Path) -> list[dict]:
    """Check for expected project files."""
    issues = []
    for filename, description in EXPECTED_FILES.items():
        if not (root / filename).exists():
            issues.append({
                "severity": "WARN",
                "type": "project_file",
                "message": f"Ontbrekend bestand: {filename} ({description})",
                "fix": f"touch {filename}  # en vul de inhoud",
            })
    return issues


def fix_issues(issues: list[dict], root: Path) -> list[dict]:
    """Try to auto-fix certain issues."""
    fixed = []

    for issue in issues:
        fix = issue.get("fix", "")
        if not fix:
            continue

        # Only fix certain types
        if issue["type"] == "init":
            # Create __init__.py
            rel_path = issue["message"].split(": ")[-1] if ": " in issue["message"] else ""
            if rel_path:
                init_path = root / rel_path / "__init__.py"
                try:
                    init_path.parent.mkdir(parents=True, exist_ok=True)
                    init_path.write_text("", encoding="utf-8")
                    fixed.append(f" ✅ Gemaakt: {init_path.relative_to(root)}")
                except Exception as e:
                    fixed.append(f" ❌ Fout bij maken {init_path}: {e}")

        elif issue["type"] == "orphaned":
            # Only fix if explicitly told
            pass

    return fixed


def print_report(all_issues: list[dict], fixed: list[dict] = None) -> None:
    """Print a formatted health report."""
    by_type = defaultdict(list)
    for issue in all_issues:
        by_type[issue["type"]].append(issue)

    warnings = [i for i in all_issues if i["severity"] == "WARN"]
    infos = [i for i in all_issues if i["severity"] == "INFO"]

    print(f"\n{'='*60}")
    print(f" 🩺 PROJECT DOCTOR — {len(all_issues)} bevinding(en)")
    print(f"{'='*60}")
    print(f"   ⚠  Warnings: {len(warnings)}")
    print(f"   💡 Info:     {len(infos)}")
    print()

    type_names = {
        "structure": "Project Structuur",
        "init": "Python Packages",
        "orphaned": "Orphaned/Residual Bestanden",
        "empty_dir": "Lege Directories",
        "large_file": "Grote Bestanden",
        "naming": "Naamgeving Conventies",
        "git": "Git Status",
        "project_file": "Project Bestanden",
    }

    for type_key, issues in sorted(by_type.items()):
        type_name = type_names.get(type_key, type_key)
        print(f"\n ── {type_name} ({len(issues)}) ──")
        for issue in issues:
            icon = "⚠" if issue["severity"] == "WARN" else "💡"
            print(f"   {icon} {issue['message']}")
            if issue.get("detail"):
                print(f"      {issue['detail']}")
            if issue.get("fix"):
                print(f"      🔧 {issue['fix']}")

    if fixed:
        print(f"\n ── Auto-fixes ({len(fixed)}) ──")
        for f in fixed:
            print(f"   {f}")

    if not all_issues:
        print(" ✅ Project ziet er gezond uit!")
    print()


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="project_doctor.py — Diagnose project health and structure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python project_doctor.py .
  python project_doctor.py src/ --json
  python project_doctor.py . --fix
  python project_doctor.py . --deep
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root directory")
    parser.add_argument("--fix", "-f", action="store_true", help="Probeer auto-fixes")
    parser.add_argument("--deep", action="store_true", help="Diepere analyse (naming, large files)")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--version", action="version", version="project_doctor.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 Project Doctor v1.0.0 — diagnosing {target}")

    all_issues = []
    all_issues.extend(diagnose_structure(target))
    all_issues.extend(find_missing_init_files(target))
    all_issues.extend(find_orphaned_files(target))
    all_issues.extend(find_empty_dirs(target))
    all_issues.extend(check_project_files(target))
    all_issues.extend(check_git_status(target))

    if args.deep:
        all_issues.extend(find_large_files(target))
        all_issues.extend(check_naming_conventions(target))

    fixed = []
    if args.fix:
        fixed = fix_issues(all_issues, target)

    if args.json:
        output = {
            "total": len(all_issues),
            "warnings": len([i for i in all_issues if i["severity"] == "WARN"]),
            "infos": len([i for i in all_issues if i["severity"] == "INFO"]),
            "issues": all_issues,
            "fixed": fixed,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print_report(all_issues, fixed)


if __name__ == "__main__":
    main()
