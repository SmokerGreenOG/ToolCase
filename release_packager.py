#!/usr/bin/env python3
"""
release_packager.py — Create a sanitised release package with full validation.

Pipeline:
  1. Preflight checks (git status, directory sanity)
  2. Security check (no .env files, no hardcoded API keys/secrets)
  3. Package metadata validation (pyproject.toml / setup.py / Cargo.toml / package.json)
  4. Run tests (pytest, unittest, cargo test, npm test — auto-detected)
  5. Run build (auto-detected)
  6. Clean temporary files (__pycache__, .bak, .pyc, build artifacts)
  7. Create release folder
  8. Generate CHANGELOG.md from git history
  9. Generate INSTALL.md instructions
  10. Create release .zip archive

BLOCKING conditions (exit code 1):
  - .env file found in release staging
  - Hardcoded API keys / secrets found in staged files
  - Tests fail (non-zero exit)
  - Build fails (non-zero exit)
  - Package metadata (name/version) cannot be determined

Usage:
    python release_packager.py <path>
    python release_packager.py <path> --version X.Y.Z
    python release_packager.py <path> --json
    python release_packager.py <path> --skip-tests
    python release_packager.py <path> --skip-build
    python release_packager.py <path> --dry-run
"""

__maker__ = "SmokerGreenOG"

import _protect

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from safe_run import SafeRunResult, safe_run
from safe_delete import safe_rmtree

# ---------------------------------------------------------------------------
# Constants & exit codes
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_BLOCKED = 1  # A blocking condition was found
EXIT_ERROR = 2  # Script-level error

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
        ".idea",
        ".vscode",
        "coverage",
        ".nyc_output",
        ".backups",
        ".rsi_backups",
        ".rsi_reports",
        ".self_improve_reports",
    }
)

EXCLUDE_PATTERNS = frozenset(
    {
        "*.pyc",
        "*.pyo",
        "*.bak",
        "*.orig",
        "*.rej",
        "*.swp",
        "*.swo",
        "*.log",
        "*.tmp",
        "*.temp",
        "Thumbs.db",
        ".DS_Store",
    }
)

SUPPRESSION_MARKER = "toolcase: ignore-security"

# API key / secret patterns (subset of security_scan.py patterns)
API_KEY_PATTERNS: list[re.Pattern] = [
    re.compile(
        r'(?i)(?:api[_-]?key|apikey|api[_-]?secret|api_secret)\s*[=:]\s*["\']([^"\'\\s]{8,})["\']'
    ),
    re.compile(r'(?i)(?:password|pwd|passwd|secret)\s*[=:]\s*["\']([^"\'\\s]{4,})["\']'),
    re.compile(
        r'(?i)(?:token|bearer|jwt|auth_token|access_token|refresh_token)\s*[=:]\s*["\']([^"\'\\s]{8,})["\']'
    ),
    re.compile(r"(?i)AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r'(?i)(?:mongodb|postgresql|mysql|redis|amqp|rabbitmq)://[^"\'\\s]+:[^"\'\\s]+@'),
]

TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
RELEASE_DIR_NAME = "release"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(
    cmd: list[str], cwd: Path, timeout: int = 300, check: bool = False
) -> SafeRunResult:
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


def _is_excluded(rel_path: str) -> bool:
    """Check if a relative path should be excluded from release."""
    parts = rel_path.replace("\\", "/").split("/")
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith("*"):
            if rel_path.endswith(pattern[1:]):
                return True
    return False


def _find_files(root: Path, pattern: str = "*") -> list[Path]:
    """Find files recursively, excluding standard ignore dirs. Rejects symlinks."""
    results = []
    for p in root.rglob(pattern):
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if _is_excluded(str(rel)):
            continue
        if p.is_file() and not p.is_symlink():
            results.append(p)
    return results


def _print_step(step: str, status: str = "") -> None:
    """Print a formatted step header."""
    icon = (
        "✅" if status == "ok" else "❌" if status == "fail" else "🔍" if status == "skip" else "→"
    )
    print(f"  {icon}  {step}")


# ---------------------------------------------------------------------------
# 1. Preflight checks
# ---------------------------------------------------------------------------


def run_preflight_checks(root: Path) -> list[dict]:
    """Run preflight health checks before building release."""
    issues = []

    # Check root exists
    if not root.exists():
        issues.append(
            {"severity": "ERROR", "type": "preflight", "message": f"Path does not exist: {root}"}
        )
        return issues

    if not root.is_dir():
        issues.append(
            {
                "severity": "ERROR",
                "type": "preflight",
                "message": f"Path is not a directory: {root}",
            }
        )
        return issues

    # Git check
    git_dir = root / ".git"
    if not git_dir.exists():
        issues.append(
            {
                "severity": "WARN",
                "type": "preflight",
                "message": "Not a git repository — changelog generation will be limited",
            }
        )
    else:
        result = _run(["git", "-C", str(root), "status", "--porcelain"], root)
        uncommitted = [l for l in result.stdout.split("\n") if l.strip()]
        if uncommitted:
            issues.append(
                {
                    "severity": "WARN",
                    "type": "preflight",
                    "message": f"{len(uncommitted)} uncommitted change(s) — consider committing first",
                    "detail": result.stdout.strip()[:500],
                }
            )

    # Basic file structure
    readme = root / "README.md"
    if not readme.exists():
        issues.append(
            {
                "severity": "WARN",
                "type": "preflight",
                "message": "README.md not found — release should include documentation",
            }
        )

    gitignore = root / ".gitignore"
    if not gitignore.exists():
        issues.append(
            {
                "severity": "INFO",
                "type": "preflight",
                "message": ".gitignore not found — consider adding one",
            }
        )

    return issues


# ---------------------------------------------------------------------------
# 2. Security check — block if .env or API keys found
# ---------------------------------------------------------------------------


def check_env_and_secrets(root: Path) -> list[dict]:
    """Check for .env files and hardcoded secrets. Blocking if found."""
    issues = []

    # Find any .env files (including .env.* variants)
    env_files: list[Path] = []
    rel_env_paths: list[str] = []
    for p in root.rglob(".env*"):
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        name = p.name
        # Only catch .env, .env.example, .env.local, .env.production etc.
        # Skip .env.example which is safe
        if name == ".env.example":
            continue
        if name.startswith(".env"):
            if p.is_file():
                env_files.append(p)
                rel_env_paths.append(str(rel))

    for env_file in env_files:
        issues.append(
            {
                "severity": "ERROR",
                "type": "secret",
                "message": f".env file found in release staging: {rel_env_paths.pop(0)}",
                "fix": "Remove .env files or add to .gitignore before releasing",
                "blocking": True,
            }
        )

    # Scan source files for hardcoded API keys/secrets
    source_extensions = {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".rs",
        ".go",
        ".java",
        ".sh",
        ".yml",
        ".yaml",
        ".toml",
        ".cfg",
        ".conf",
        ".ini",
        ".env.example",
    }
    scanned = 0
    for p in _find_files(root):
        ext = p.suffix.lower()
        if ext not in source_extensions:
            continue
        if p.name == ".env.example":
            continue
        try:
            content = _safe_read(p)
        except Exception:
            continue
        if not content:
            continue
        # Skip binary-looking files
        if "\0" in content:
            continue
        # Build a set of suppressed line numbers
        suppressed_lines: set[int] = set()
        for i, line in enumerate(content.splitlines(), 1):
            if SUPPRESSION_MARKER in line:
                suppressed_lines.add(i)

        for pattern in API_KEY_PATTERNS:
            matches = []
            for m in pattern.finditer(content):
                # Check if this match is on a suppressed line
                line_no = content[: m.start()].count("\n") + 1
                if line_no not in suppressed_lines:
                    matches.append(m.group())
            if matches:
                try:
                    rel_path = p.relative_to(root)
                except ValueError:
                    rel_path = p
                # Redact the actual secret for display
                for m in matches:
                    displayed = m[:6] + "..." if len(m) > 8 else "(redacted)"
                    issues.append(
                        {
                            "severity": "ERROR",
                            "type": "secret",
                            "message": f"Potential secret found in {rel_path}: '{displayed}'",
                            "pattern": pattern.pattern[:50] + "...",
                            "blocking": True,
                        }
                    )
        scanned += 1

    if scanned > 0:
        _print_step(f"Scanned {scanned} source files for secrets", "ok" if not issues else "fail")

    return issues


# ---------------------------------------------------------------------------
# 3. Package metadata check
# ---------------------------------------------------------------------------


def check_metadata(root: Path) -> tuple[dict, list[dict]]:
    """Extract package metadata (name, version) from common config files. Blocking if missing."""
    issues = []
    metadata: dict[str, Any] = {"name": None, "version": None, "type": None}

    # pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        content = _safe_read(pyproject)
        m_name = re.search(r'^name\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
        m_ver = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
        if m_name:
            metadata["name"] = m_name.group(1)
        if m_ver:
            metadata["version"] = m_ver.group(1)
        metadata["type"] = "python"

    # setup.py
    if not metadata["name"]:
        setup = root / "setup.py"
        if setup.exists():
            content = _safe_read(setup)
            m_name = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
            m_ver = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if m_name:
                metadata["name"] = m_name.group(1)
            if m_ver:
                metadata["version"] = m_ver.group(1)
            metadata["type"] = "python"

    # package.json
    if not metadata["name"]:
        pkg_json = root / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(_safe_read(pkg_json))
                metadata["name"] = data.get("name")
                metadata["version"] = data.get("version")
                metadata["type"] = "node"
            except (json.JSONDecodeError, Exception):
                pass

    # Cargo.toml
    if not metadata["name"]:
        cargo = root / "Cargo.toml"
        if cargo.exists():
            content = _safe_read(cargo)
            m_name = re.search(r'^name\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
            m_ver = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
            if m_name:
                metadata["name"] = m_name.group(1)
            if m_ver:
                metadata["version"] = m_ver.group(1)
            metadata["type"] = "rust"

    # Fallback: __init__.py
    if not metadata["name"] or not metadata["version"]:
        init = root / "__init__.py"
        if init.exists():
            content = _safe_read(init)
            if not metadata["name"]:
                m_name = re.search(r'__maker__\s*=\s*["\']([^"\']+)["\']', content)
                if m_name:
                    metadata["name"] = f"ToolCase ({m_name.group(1)})"
            if not metadata["version"]:
                m_ver = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
                if m_ver:
                    metadata["version"] = m_ver.group(1)
            metadata["type"] = "python"

    if not metadata["name"]:
        issues.append(
            {
                "severity": "ERROR",
                "type": "metadata",
                "message": "Could not determine package name — no pyproject.toml, setup.py, package.json, or Cargo.toml found",
                "blocking": True,
            }
        )

    if not metadata["version"]:
        issues.append(
            {
                "severity": "ERROR",
                "type": "metadata",
                "message": "Could not determine package version — no version found in any config file",
                "blocking": True,
            }
        )

    return metadata, issues


# ---------------------------------------------------------------------------
# 4. Run tests
# ---------------------------------------------------------------------------


def run_tests(root: Path) -> list[dict]:
    """Auto-detect and run tests. Blocking if tests fail."""
    issues = []
    test_ran = False

    # Python: pytest
    if _which("pytest") or (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        test_files = (
            list(root.rglob("test_*.py"))
            + list(root.rglob("*_test.py"))
            + list(root.rglob("tests/*.py"))
        )
        if test_files:
            test_ran = True
            _print_step("Running Python tests (pytest)...")
            cmd = ["pytest", "-x", "--tb=short", "-q"]
            if not _which("pytest"):
                # Try via python -m pytest
                cmd = [sys.executable, "-m", "pytest", "-x", "--tb=short", "-q"]
            result = _run(cmd, root, timeout=300)
            if result.returncode == 0:
                _print_step("Python tests passed", "ok")
            else:
                _print_step("Python tests failed", "fail")
                issues.append(
                    {
                        "severity": "ERROR",
                        "type": "test",
                        "message": f"Python tests failed (exit code {result.returncode})",
                        "detail": (result.stdout + result.stderr)[:2000],
                        "blocking": True,
                    }
                )

    # Node: npm test
    if not test_ran and (root / "package.json").exists():
        pkg = (
            json.loads(_safe_read(root / "package.json"))
            if _safe_read(root / "package.json")
            else {}
        )
        if "scripts" in pkg and "test" in pkg["scripts"]:
            test_ran = True
            _print_step("Running npm test...")
            result = _run(["npm", "test"], root, timeout=300)
            if result.returncode == 0:
                _print_step("npm tests passed", "ok")
            else:
                _print_step("npm tests failed", "fail")
                issues.append(
                    {
                        "severity": "ERROR",
                        "type": "test",
                        "message": f"npm test failed (exit code {result.returncode})",
                        "detail": (result.stdout + result.stderr)[:2000],
                        "blocking": True,
                    }
                )

    # Rust: cargo test
    if not test_ran and (root / "Cargo.toml").exists() and _which("cargo"):
        test_ran = True
        _print_step("Running cargo test...")
        result = _run(["cargo", "test"], root, timeout=600)
        if result.returncode == 0:
            _print_step("Rust tests passed", "ok")
        else:
            _print_step("Rust tests failed", "fail")
            issues.append(
                {
                    "severity": "ERROR",
                    "type": "test",
                    "message": f"cargo test failed (exit code {result.returncode})",
                    "detail": (result.stdout + result.stderr)[:2000],
                    "blocking": True,
                }
            )

    if not test_ran:
        _print_step("No tests discovered — skipping", "skip")
        issues.append(
            {
                "severity": "INFO",
                "type": "test",
                "message": "No test runner detected (pytest, npm test, cargo test)",
            }
        )

    return issues


# ---------------------------------------------------------------------------
# 5. Run build
# ---------------------------------------------------------------------------


def run_build(root: Path, version_override: str | None = None) -> list[dict]:
    """Auto-detect and run build. Blocking if build fails."""
    issues = []
    build_ran = False

    # Python build (if pyproject.toml has build backend)
    if (root / "pyproject.toml").exists():
        content = _safe_read(root / "pyproject.toml")
        if "build-backend" in content:
            build_ran = True
            _print_step("Building Python package...")
            # Check if build module is installed
            result = _run(
                [sys.executable, "-m", "build", "--sdist", "--wheel", "."], root, timeout=300
            )
            if result.returncode == 0:
                _print_step("Python build succeeded", "ok")
            elif (
                "No module named build" in result.stderr or "No module named build" in result.stdout
            ):
                _print_step("Python build skipped (pip install build first)", "skip")
                issues.append(
                    {
                        "severity": "WARN",
                        "type": "build",
                        "message": "Python build module not installed — run: pip install build",
                    }
                )
                build_ran = False
            else:
                _print_step("Python build failed", "fail")
                issues.append(
                    {
                        "severity": "ERROR",
                        "type": "build",
                        "message": f"Python build failed (exit code {result.returncode})",
                        "detail": (result.stdout + result.stderr)[:2000],
                        "blocking": True,
                    }
                )

    # Node: npm run build
    if not build_ran and (root / "package.json").exists():
        pkg = (
            json.loads(_safe_read(root / "package.json"))
            if _safe_read(root / "package.json")
            else {}
        )
        if "scripts" in pkg and "build" in pkg["scripts"]:
            build_ran = True
            _print_step("Running npm run build...")
            result = _run(["npm", "run", "build"], root, timeout=300)
            if result.returncode == 0:
                _print_step("npm build succeeded", "ok")
            else:
                _print_step("npm build failed", "fail")
                issues.append(
                    {
                        "severity": "ERROR",
                        "type": "build",
                        "message": f"npm run build failed (exit code {result.returncode})",
                        "detail": (result.stdout + result.stderr)[:2000],
                        "blocking": True,
                    }
                )

    # Rust: cargo build
    if not build_ran and (root / "Cargo.toml").exists() and _which("cargo"):
        build_ran = True
        _print_step("Running cargo build...")
        result = _run(["cargo", "build", "--release"], root, timeout=600)
        if result.returncode == 0:
            _print_step("Rust build succeeded", "ok")
        else:
            _print_step("Rust build failed", "fail")
            issues.append(
                {
                    "severity": "ERROR",
                    "type": "build",
                    "message": f"cargo build --release failed (exit code {result.returncode})",
                    "detail": (result.stdout + result.stderr)[:2000],
                    "blocking": True,
                }
            )

    if not build_ran:
        _print_step("No build system detected — skipping build step", "skip")

    return issues


# ---------------------------------------------------------------------------
# 6. Clean temporary files
# ---------------------------------------------------------------------------


def clean_temp_files(root: Path) -> int:
    """Remove temporary/build artifacts. Returns count of cleaned items."""
    cleaned = 0

    patterns_to_clean = [
        "__pycache__",
        "*.pyc",
        "*.pyo",
        "*.bak",
        "*.orig",
        "*.rej",
        "*.swp",
        "*.swo",
        "Thumbs.db",
        ".DS_Store",
    ]

    # Clean __pycache__ directories
    for p in list(root.rglob("__pycache__")):
        if p.is_dir() and not _is_excluded(str(p.relative_to(root)) if p != root else ""):
            try:
                safe_rmtree(p, workspace=root, force=True)
                cleaned += 1
            except Exception:
                pass

    # Clean temp file patterns
    for pattern in patterns_to_clean:
        if pattern == "__pycache__":
            continue  # Already handled above
        for p in root.rglob(pattern):
            if p.is_file():
                try:
                    p.unlink()
                    cleaned += 1
                except Exception:
                    pass

    # Clean build/ directory (intermediate build artifacts only).
    # Do NOT clean dist/ — it contains the built wheel and sdist.
    build_dir = root / "build"
    if build_dir.exists() and build_dir.is_dir():
        safe_rmtree(build_dir, workspace=root, force=True)
        cleaned += 1

    return cleaned


# ---------------------------------------------------------------------------
# 7. Create release folder
# ---------------------------------------------------------------------------


def create_release_folder(
    root: Path, metadata: dict, version_override: str | None = None
) -> Path | None:
    """Create a timestamped release folder. Returns the path or None on failure."""
    name = metadata.get("name", "project")
    version = version_override or metadata.get("version", "0.0.0")
    timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(name))
    safe_version = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(version))

    release_dir_name = f"{safe_name}-v{safe_version}-{timestamp}"
    release_path = root / RELEASE_DIR_NAME / release_dir_name

    try:
        release_path.mkdir(parents=True, exist_ok=True)
        _print_step(f"Created release folder: {release_path}")
        return release_path
    except OSError as e:
        _print_step(f"Failed to create release folder: {e}", "fail")
        return None


# ---------------------------------------------------------------------------
# 8. Generate changelog
# ---------------------------------------------------------------------------


def create_changelog(
    root: Path, release_path: Path, metadata: dict, version_override: str | None = None
) -> Path | None:
    """Generate a CHANGELOG.md from git history. Returns path or None."""
    version = version_override or metadata.get("version", "0.0.0")
    name = metadata.get("name", "Project")
    changelog_path = release_path / "CHANGELOG.md"

    lines = [
        f"# Changelog — {name} v{version}",
        "",
        f"Release generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    # Try git log
    git_dir = root / ".git"
    if git_dir.exists() and _which("git"):
        result = _run(
            ["git", "-C", str(root), "log", "--oneline", "--no-decorate", "-50"],
            root,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            commits = [l.strip() for l in result.stdout.split("\n") if l.strip()]
            lines.append("## What's Changed")
            lines.append("")
            for commit in commits:
                lines.append(f"- {commit}")
            lines.append("")

            # Also get latest tag
            tag_result = _run(
                ["git", "-C", str(root), "describe", "--tags", "--abbrev=0"],
                root,
                timeout=10,
            )
            if tag_result.returncode == 0 and tag_result.stdout.strip():
                tag = tag_result.stdout.strip()
                lines.append(f"> Based on tag: `{tag}`")
                lines.append("")
        else:
            lines.append("*No git history available.*")
            lines.append("")
    else:
        lines.append("*Git repository not found — changelog generated without history.*")
        lines.append("")

    # Add file manifest
    lines.append("## Included Files")
    lines.append("")
    lines.append("See the release archive for the complete file manifest.")
    lines.append("")

    try:
        changelog_path.write_text("\n".join(lines), encoding="utf-8")
        _print_step(f"Created CHANGELOG.md ({len(commits) if 'commits' in dir() else 0} commits)")
        return changelog_path
    except OSError as e:
        _print_step(f"Failed to write CHANGELOG.md: {e}", "fail")
        return None


# ---------------------------------------------------------------------------
# 9. Generate install instructions
# ---------------------------------------------------------------------------


def create_install_instructions(
    release_path: Path, metadata: dict, version_override: str | None = None
) -> Path | None:
    """Generate INSTALL.md with setup instructions. Returns path or None."""
    version = version_override or metadata.get("version", "0.0.0")
    name = metadata.get("name", "Project")
    pkg_type = metadata.get("type", "python")
    install_path = release_path / "INSTALL.md"

    lines = [
        f"# Install — {name} v{version}",
        "",
        f"## Prerequisites",
        "",
    ]

    if pkg_type == "python":
        lines.extend(
            [
                "- Python 3.11 or higher",
                "- pip (Python package installer)",
                "",
                "## Quick Install",
                "",
                "```bash",
                "# Install from the release archive",
                f"cd {name}-v{version}",
                "pip install .",
                "",
                "# Verify the installation",
                "toolcase --version",
                "toolcase --verify-install",
                "```",
                "",
                "## Hermes Skill Installation",
                "",
                "For use as a Hermes Agent skill:",
                "```bash",
                "mkdir -p ~/.hermes/skills/toolcase-self-improve",
                "cp SKILL.md manifest.json ~/.hermes/skills/toolcase-self-improve/",
                "cp -r scripts/ references/ ~/.hermes/skills/toolcase-self-improve/",
                "```",
            ]
        )
    elif pkg_type == "node":
        lines.extend(
            [
                "- Node.js 16 or higher",
                "- npm or yarn",
                "",
                "## Quick Install",
                "",
                "```bash",
                f"cd {name}-v{version}",
                "npm install",
                "",
                "# Development",
                "npm run dev",
                "",
                "# Production build",
                "npm run build",
                "npm start",
                "```",
            ]
        )
    elif pkg_type == "rust":
        lines.extend(
            [
                "- Rust toolchain (rustc, cargo)",
                "",
                "## Quick Install",
                "",
                "```bash",
                f"cd {name}-v{version}",
                "cargo build --release",
                f"./target/release/{name}",
                "```",
            ]
        )
    else:
        lines.extend(
            [
                "- Appropriate runtime for the project",
                "",
                "## Quick Install",
                "",
                "```bash",
                f"cd {name}-v{version}",
                "# See README.md for specific setup instructions",
                "```",
            ]
        )

    lines.extend(
        [
            "",
            "## Verification",
            "",
            "```bash",
            "# Check that everything is working",
            "# (project-specific verification steps)",
            "```",
            "",
            "---",
            f"*Generated by release_packager.py on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            "",
        ]
    )

    try:
        install_path.write_text("\n".join(lines), encoding="utf-8")
        _print_step("Created INSTALL.md")
        return install_path
    except OSError as e:
        _print_step(f"Failed to write INSTALL.md: {e}", "fail")
        return None


# ---------------------------------------------------------------------------
# 10. Create release zip
# ---------------------------------------------------------------------------


def create_release_zip(
    root: Path, release_path: Path, metadata: dict, version_override: str | None = None
) -> Path | None:
    """Copy project files into release folder and create a zip archive."""
    version = version_override or metadata.get("version", "0.0.0")
    name = metadata.get("name", "project")
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(name))
    safe_version = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(version))

    # Copy project files (excluding ignored dirs / patterns) into release folder
    _print_step("Copying project files to release folder...")
    copied = 0
    skipped = 0
    copied_files: list[Path] = []

    for p in _find_files(root):
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        rel_str = str(rel).replace("\\", "/")

        # Skip .env files entirely
        if rel.name.startswith(".env") and rel.name != ".env.example":
            skipped += 1
            continue

        # Skip release folder itself
        if rel_str.startswith(RELEASE_DIR_NAME):
            continue

        target = release_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(p, target)
            copied += 1
            copied_files.append(rel)
        except Exception:
            skipped += 1

    _print_step(f"Copied {copied} files ({skipped} skipped or filtered)")

    # Create the .zip file
    timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
    zip_name = f"{safe_name}-v{safe_version}-{timestamp}.zip"
    zip_path = root / RELEASE_DIR_NAME / zip_name

    _print_step(f"Creating archive: {zip_name}...")
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in release_path.rglob("*"):
                if file_path.is_file():
                    arcname = str(file_path.relative_to(release_path))
                    zf.write(file_path, arcname)
        _print_step(f"Created zip archive ({_human_size(zip_path.stat().st_size)})", "ok")
        return zip_path
    except OSError as e:
        _print_step(f"Failed to create zip archive: {e}", "fail")
        return None


def _human_size(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# ---------------------------------------------------------------------------
# Report & output
# ---------------------------------------------------------------------------


def format_report(
    preflight: list[dict],
    secrets: list[dict],
    metadata: tuple[dict, list[dict]],
    tests: list[dict],
    build: list[dict],
    cleaned_count: int,
    release_dir: Path | None,
    changelog: Path | None,
    install_file: Path | None,
    zip_path: Path | None,
    all_issues: list[dict],
    dry_run: bool,
) -> dict:
    """Compile structured report from all steps."""
    metadata_info, metadata_issues = metadata

    blocking_issues = [i for i in all_issues if i.get("blocking")]
    warnings = [i for i in all_issues if i["severity"] == "WARN"]
    infos = [i for i in all_issues if i["severity"] == "INFO"]
    errors = [i for i in all_issues if i["severity"] == "ERROR"]

    report: dict[str, Any] = {
        "success": len(blocking_issues) == 0,
        "dry_run": dry_run,
        "package": {
            "name": metadata_info.get("name"),
            "version": metadata_info.get("version"),
            "type": metadata_info.get("type"),
        },
        "pipeline": {
            "preflight": {
                "ok": len([i for i in preflight if i["severity"] == "ERROR"]) == 0,
                "issues": len(preflight),
            },
            "secrets": {"ok": len(secrets) == 0, "issues": len(secrets)},
            "metadata": {"ok": len(metadata_issues) == 0, "issues": len(metadata_issues)},
            "tests": {
                "ok": len([i for i in tests if i["severity"] == "ERROR"]) == 0,
                "issues": len(tests),
            },
            "build": {
                "ok": len([i for i in build if i["severity"] == "ERROR"]) == 0,
                "issues": len(build),
            },
        },
        "cleaned_files": cleaned_count,
        "release_folder": str(release_dir) if release_dir else None,
        "changelog": str(changelog) if changelog else None,
        "install_file": str(install_file) if install_file else None,
        "zip_path": str(zip_path) if zip_path else None,
        "issues": {
            "total": len(all_issues),
            "blocking": len(blocking_issues),
            "errors": len(errors),
            "warnings": len(warnings),
            "infos": len(infos),
        },
        "all_issues": all_issues,
    }

    return report


def print_report(report: dict) -> None:
    """Print a human-readable release report."""
    meta = report["package"]
    pipeline = report["pipeline"]
    issues = report["issues"]

    print(f"\n{'=' * 60}")
    status = "✅ RELEASE READY" if report["success"] else "❌ RELEASE BLOCKED"
    print(f" {status}")
    print(
        f" Package: {meta.get('name', 'Unknown')} v{meta.get('version', '?')} ({meta.get('type', '?')})"
    )
    if report["dry_run"]:
        print(f" 🏁 Dry-run mode — no files were actually packaged")
    print(f"{'=' * 60}")

    print(f"\n 📋 Pipeline Summary:")
    print(
        f"    🔍 Preflight:    {'✅' if pipeline['preflight']['ok'] else '⚠'}  ({pipeline['preflight']['issues']} issues)"
    )
    print(
        f"    🔒 Secrets:      {'✅' if pipeline['secrets']['ok'] else '❌'}  ({pipeline['secrets']['issues']} issues)"
    )
    print(
        f"    📦 Metadata:     {'✅' if pipeline['metadata']['ok'] else '❌'}  ({pipeline['metadata']['issues']} issues)"
    )
    print(
        f"    🧪 Tests:        {'✅' if pipeline['tests']['ok'] else '❌'}  ({pipeline['tests']['issues']} issues)"
    )
    print(
        f"    🏗  Build:        {'✅' if pipeline['build']['ok'] else '❌'}  ({pipeline['build']['issues']} issues)"
    )

    if report["cleaned_files"] > 0:
        print(f"    🧹 Cleaned:      {report['cleaned_files']} temp file(s) removed")
    else:
        print(f"    🧹 Cleaned:      No temp files found")

    print(f"\n 📦 Output:")
    print(f"    📁 Release:      {report['release_folder'] or 'N/A'}")
    print(f"    📝 Changelog:    {report['changelog'] or 'N/A'}")
    print(f"    📖 Install:      {report['install_file'] or 'N/A'}")
    print(f"    🗜  Archive:      {report['zip_path'] or 'N/A'}")

    if issues["total"] > 0:
        print(f"\n ⚠  Issues ({issues['total']} total):")
        print(
            f"    🔴 Blocking: {issues['blocking']}  |  🟡 Errors: {issues['errors']}  |  🟠 Warnings: {issues['warnings']}  |  🔵 Info: {issues['infos']}"
        )

        # Show blocking issues prominently
        blocking = [i for i in report["all_issues"] if i.get("blocking")]
        if blocking:
            print(f"\n 🚫 Blocking Issues (must be resolved):")
            for i, issue in enumerate(blocking, 1):
                print(f"   {i}. {issue['message']}")
                if issue.get("fix"):
                    print(f"      🔧 Fix: {issue['fix']}")

        # Show warnings
        warnings_list = [
            i for i in report["all_issues"] if i["severity"] == "WARN" and not i.get("blocking")
        ]
        if warnings_list:
            print(f"\n ⚠  Warnings:")
            for issue in warnings_list:
                print(f"   • {issue['message']}")

    if report["success"]:
        print(f"\n {'✅' * 20}")
        print(f"   Release package is ready!")
        print(f"   Archive: {report['zip_path']}")
        print(f"   {'✅' * 20}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="release_packager.py — Create a sanitised release package with full validation pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python release_packager.py .                          # Full pipeline
  python release_packager.py . --version 2.1.0          # Override version
  python release_packager.py . --json                   # JSON output
  python release_packager.py . --skip-tests             # Skip test step
  python release_packager.py . --skip-build             # Skip build step
  python release_packager.py . --dry-run                # Check only, no packaging
  python release_packager.py . --skip-tests --skip-build  # Quick check only
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root directory")
    parser.add_argument("--version", "-V", metavar="X.Y.Z", help="Override version number")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument("--skip-tests", action="store_true", help="Skip test execution step")
    parser.add_argument("--skip-build", action="store_true", help="Skip build step")
    parser.add_argument(
        "--dry-run", action="store_true", help="Run all checks but do not package anything"
    )
    parser.add_argument("--no-clean", action="store_true", help="Skip cleaning temporary files")
    return parser


def main() -> None:
    """main."""
    parser = build_arg_parser()
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.exists():
        print(f" ❌ Path does not exist: {args.path}", file=sys.stderr)
        sys.exit(EXIT_ERROR)
    if not root.is_dir():
        print(f" ❌ Path is not a directory: {args.path}", file=sys.stderr)
        sys.exit(EXIT_ERROR)

    version_override = args.version
    skip_tests = args.skip_tests
    skip_build = args.skip_build
    dry_run = args.dry_run
    no_clean = args.no_clean

    all_issues: list[dict] = []
    release_dir: Path | None = None
    changelog_path: Path | None = None
    install_path: Path | None = None
    zip_path: Path | None = None
    cleaned_count = 0

    # Print header
    print(f"\n{'=' * 60}")
    print(f" 📦 RELEASE PACKAGER")
    print(f" {'=' * 60}")
    print(f" Target:   {root}")
    print(f" Dry-run:  {'Yes' if dry_run else 'No'}")
    print(f" Tests:    {'Skipped' if skip_tests else 'Yes'}")
    print(f" Build:    {'Skipped' if skip_build else 'Yes'}")
    print(f" Version:  {version_override or '(auto)'}")
    print()

    # ── Step 1: Preflight ──────────────────────────────────────
    _print_step("Running preflight checks...")
    preflight = run_preflight_checks(root)
    all_issues.extend(preflight)
    if any(i["severity"] == "ERROR" for i in preflight):
        # Fatal preflight error (path doesn't exist etc.)
        if args.json:
            print(
                json.dumps(
                    {
                        "success": False,
                        "dry_run": dry_run,
                        "package": {"name": None, "version": None, "type": None},
                        "pipeline": {},
                        "issues": {
                            "total": len(all_issues),
                            "blocking": 0,
                            "errors": 0,
                            "warnings": 0,
                            "infos": 0,
                        },
                        "all_issues": all_issues,
                    },
                    indent=2,
                )
            )
        else:
            print(f"\n ❌ Preflight checks failed — aborting")
        sys.exit(EXIT_BLOCKED)

    # ── Step 2: Security check ─────────────────────────────────
    _print_step("Scanning for secrets and .env files...")
    secrets = check_env_and_secrets(root)
    all_issues.extend(secrets)
    blocking_secrets = [i for i in secrets if i.get("blocking")]
    if blocking_secrets:
        if args.json:
            # Build partial report
            report = format_report(
                preflight,
                secrets,
                ({"name": None, "version": None, "type": None}, []),
                [],
                [],
                0,
                None,
                None,
                None,
                None,
                all_issues,
                dry_run,
            )
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"\n ❌ Blocking secrets found — release aborted")
            for issue in blocking_secrets:
                print(f"   • {issue['message']}")
        sys.exit(EXIT_BLOCKED)

    # ── Step 3: Metadata check ─────────────────────────────────
    _print_step("Checking package metadata...")
    metadata_info, metadata_issues = check_metadata(root)
    all_issues.extend(metadata_issues)
    blocking_meta = [i for i in metadata_issues if i.get("blocking")]
    if blocking_meta:
        if args.json:
            report = format_report(
                preflight,
                secrets,
                (metadata_info, metadata_issues),
                [],
                [],
                0,
                None,
                None,
                None,
                None,
                all_issues,
                dry_run,
            )
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"\n ❌ Package metadata missing — release aborted")
            for issue in blocking_meta:
                print(f"   • {issue['message']}")
        sys.exit(EXIT_BLOCKED)

    _print_step(
        f"Package: {metadata_info['name']} v{metadata_info['version']} ({metadata_info['type']})",
        "ok",
    )

    # ── Steps 4-10: Tests, Build, Cleanup, Package (ALL skipped in dry-run) ──
    if dry_run:
        _print_step("Dry-run mode — skipping all write/cleanup/build steps", "skip")
        # Dry-run: preflight + secrets + metadata only. Zero writes.
        test_issues = []
        build_issues = []
    else:
        # ── Step 4: Run tests ────────────────────────────────
        if skip_tests:
            _print_step("Tests skipped (--skip-tests)", "skip")
        else:
            _print_step("Running tests...")
            test_issues = run_tests(root)
            all_issues.extend(test_issues)
            blocking_tests = [i for i in test_issues if i.get("blocking")]
            if blocking_tests:
                if args.json:
                    report = format_report(
                        preflight,
                        secrets,
                        (metadata_info, metadata_issues),
                        test_issues,
                        [],
                        0,
                        None,
                        None,
                        None,
                        None,
                        all_issues,
                        dry_run,
                    )
                    print(json.dumps(report, indent=2, ensure_ascii=False))
                else:
                    print(f"\n ❌ Tests failed — release aborted")
                    for issue in blocking_tests:
                        print(f"   • {issue['message']}")
                        if issue.get("detail"):
                            print(f"     {issue['detail'][:300]}")
                sys.exit(EXIT_BLOCKED)

        # ── Step 5: Run build ────────────────────────────────
        if skip_build:
            _print_step("Build skipped (--skip-build)", "skip")
        else:
            _print_step("Running build...")
            build_issues = run_build(root, version_override)
            all_issues.extend(build_issues)
            blocking_build = [i for i in build_issues if i.get("blocking")]
            if blocking_build:
                if args.json:
                    report = format_report(
                        preflight,
                        secrets,
                        (metadata_info, metadata_issues),
                        [] if skip_tests else test_issues,
                        build_issues,
                        0,
                        None,
                        None,
                        None,
                        None,
                        all_issues,
                        dry_run,
                    )
                    print(json.dumps(report, indent=2, ensure_ascii=False))
                else:
                    print(f"\n ❌ Build failed — release aborted")
                    for issue in blocking_build:
                        print(f"   • {issue['message']}")
                        if issue.get("detail"):
                            print(f"     {issue['detail'][:300]}")
                sys.exit(EXIT_BLOCKED)

        # ── Step 6: Clean temp files (NOT dist/ — that's the built artifact) ──
        if no_clean:
            _print_step("Clean skipped (--no-clean)", "skip")
        else:
            _print_step("Cleaning temporary files...")
            cleaned_count = clean_temp_files(root)
            if cleaned_count > 0:
                _print_step(f"Cleaned {cleaned_count} temporary file(s)", "ok")
            else:
                _print_step("No temporary files to clean", "ok")

        # Step 7: Create release folder
        _print_step("Creating release folder...")
        release_dir = create_release_folder(root, metadata_info, version_override)
        if release_dir is None:
            all_issues.append(
                {
                    "severity": "ERROR",
                    "type": "packaging",
                    "message": "Failed to create release folder",
                }
            )
            if args.json:
                report = format_report(
                    preflight,
                    secrets,
                    (metadata_info, metadata_issues),
                    [] if skip_tests else (test_issues if "test_issues" in dir() else []),
                    [] if skip_build else (build_issues if "build_issues" in dir() else []),
                    cleaned_count,
                    None,
                    None,
                    None,
                    None,
                    all_issues,
                    dry_run,
                )
                print(json.dumps(report, indent=2, ensure_ascii=False))
            sys.exit(EXIT_ERROR)

        # Step 8: Create changelog
        _print_step("Generating changelog...")
        changelog_path = create_changelog(root, release_dir, metadata_info, version_override)

        # Step 9: Create install instructions
        _print_step("Generating install instructions...")
        install_path = create_install_instructions(release_dir, metadata_info, version_override)

        # Step 10: Create zip archive
        _print_step("Creating release archive...")
        zip_path = create_release_zip(root, release_dir, metadata_info, version_override)

    # ── Final report ───────────────────────────────────────────
    report = format_report(
        preflight,
        secrets,
        (metadata_info, metadata_issues),
        [] if skip_tests else (locals().get("test_issues", [])),
        [] if skip_build else (locals().get("build_issues", [])),
        cleaned_count,
        release_dir,
        changelog_path,
        install_path,
        zip_path,
        all_issues,
        dry_run,
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)

    sys.exit(EXIT_OK if report["success"] else EXIT_BLOCKED)


if __name__ == "__main__":
    main()
