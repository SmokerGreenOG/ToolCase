#!/usr/bin/env python3
"""
file_guard.py — Protect important files from accidental overwrite, deletion, or rename.

Protects: .env, .env.local, .env.production, package.json, package-lock.json,
pnpm-lock.yaml, requirements.txt, pyproject.toml, vite.config.ts, next.config.js,
database files, auth files, config files, and any user-specified paths.

Usage:
    python file_guard.py check <path>          # Check if a file is protected
    python file_guard.py diff <path> [content] # Show diff before writing
    python file_guard.py protect <path>        # Attempt to write (guarded)
    python file_guard.py delete <path>         # Attempt to delete (guarded)
    python file_guard.py rename <src> <dst>    # Attempt to rename (guarded)
    python file_guard.py mass-check <paths>    # Check multiple files at once
    python file_guard.py backup <path>         # Create a backup of a file
    python file_guard.py status                # Show protected file status
    python file_guard.py --help                # Show this help

Exit codes:
    0 — All clear (file not protected or approved operation)
    1 — Protected file blocked / error occurred
    2 — User declined / required approval not given
"""

from __future__ import annotations

__maker__ = "SmokerGreenOG"

import _protect

import argparse
import difflib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Files that are always protected (case-insensitive matching for the basename)
ALWAYS_PROTECTED_BASENAMES: Set[str] = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "poetry.lock",
    "vite.config.ts",
    "vite.config.js",
    "next.config.js",
    "next.config.mjs",
    "next.config.ts",
    "tailwind.config.js",
    "tailwind.config.ts",
    "tsconfig.json",
    "tsconfig.node.json",
    ".gitignore",
    ".dockerignore",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Dockerfile",
    "Makefile",
    "Gemfile",
    "Gemfile.lock",
    ".ruby-version",
    ".node-version",
    ".nvmrc",
    "composer.json",
    "composer.lock",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "mix.exs",
    "mix.lock",
}

# Directory/file patterns that indicate DB / auth / config files
PROTECTED_PATTERNS: List[str] = [
    # Database files
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.db.sqlite3",
    "*.db3",
    "*.s3db",
    "*.mysql",
    "*.mariadb",
    "*.dump",
    "*.dmp",
    # Auth / credentials
    "*auth*",
    "*credential*",
    "*secret*",
    "*token*",
    "*key*",
    "*.pem",
    "*.key",
    "*.cert",
    "*.p12",
    "*.pfx",
    "*.jks",
    "id_rsa",
    "id_ed25519",
    ".ssh/*",
    # Config files (broad)
    "*.cfg",
    "*.conf",
    "*.ini",
    "*.toml",
    "*.yaml",
    "*.yml",
    ".editorconfig",
    ".prettierrc*",
    ".eslintrc*",
    ".stylelintrc*",
    ".browserslistrc",
    ".babelrc*",
    ".npmrc",
    ".yarnrc*",
    ".pnpmrc",
    ".ncurc*",
    # Service / cloud configs
    "firebase*",
    "serviceAccount*",
    "credentials*",
    ".aws/*",
    ".azure/*",
    ".gcp/*",
    ".kube/*",
    "kubeconfig*",
    ".terraform*",
    "*.tfvars",
    "*.tfstate*",
    "*.tfplan",
    # Environment / Docker
    ".env*",
    "*.env",
    # CI/CD
    ".github/workflows/*",
    ".gitlab-ci.yml",
    ".circleci/*",
    "Jenkinsfile*",
    # App config
    "next-env.d.ts",
    "angular.json",
    "nuxt.config*",
    "svelte.config*",
    "astro.config*",
    "remix.config*",
    "gatsby-config*",
    "gridsome.config*",
]

# Threshold for mass-edit detection (number of protected files changed)
MASS_EDIT_THRESHOLD: int = 5

# Backup directory (relative to each protected file's parent)
BACKUP_DIR_NAME: str = ".file_guard_backups"

# How long to keep backups (in seconds) — 30 days
BACKUP_RETENTION_SECONDS: int = 30 * 24 * 3600


# ---------------------------------------------------------------------------
# Core utilities
# ---------------------------------------------------------------------------


def _is_protected(path: Union[str, Path]) -> bool:
    """Check if a path is a protected file based on name and patterns."""
    p = Path(path)

    # If path doesn't exist yet, check based on the intended name
    name = p.name
    parent = str(p.parent).replace("\\", "/")

    # 1. Check exact basename match (case-insensitive on Windows)
    for protected_name in ALWAYS_PROTECTED_BASENAMES:
        if name.lower() == protected_name.lower():
            return True

    # 2. Check pattern matches (using fnmatch-style)
    import fnmatch
    for pattern in PROTECTED_PATTERNS:
        # Check against full relative path and basename
        if fnmatch.fnmatch(name, pattern):
            return True
        full = str(p).replace("\\", "/")
        # Pattern like ".ssh/*" — check parent-relative
        if "/" in pattern:
            if fnmatch.fnmatch(full, pattern) or fnmatch.fnmatch(full, "*" + pattern):
                return True
        # Pattern like "*auth*" — check against full path
        if "*" in pattern or "?" in pattern or "[" in pattern:
            if fnmatch.fnmatch(name, pattern):
                return True
            if fnmatch.fnmatch(full, pattern):
                return True
            if fnmatch.fnmatch(full, "*" + pattern):
                return True
            # Wildcard at start: match any segment
            if pattern.startswith("*"):
                if fnmatch.fnmatch(name, pattern):
                    return True
                if fnmatch.fnmatch(full, pattern):
                    return True
        else:
            # Exact substring match in the full path
            if pattern.lower() in full.lower():
                return True

    # 3. Check directory-based patterns
    # e.g., files inside .git, .ssh, .aws, etc.
    parent_lower = parent.lower()
    sensitive_dirs = [
        ".ssh", ".aws", ".azure", ".gcp", ".kube", ".gnupg",
        ".config", ".gradle", ".m2", ".nuget",
    ]
    for sdir in sensitive_dirs:
        if f"/{sdir}/" in f"/{parent_lower}/":
            return True

    return False


def _compute_backup_path(file_path: Path) -> Path:
    """Get the backup path for a given file."""
    backup_dir = file_path.parent / BACKUP_DIR_NAME
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_name = f"{file_path.name}.{timestamp}.bak"
    return backup_dir / backup_name


def _create_backup(file_path: Path) -> Optional[Path]:
    """Create a timestamped backup of the given file. Returns backup path or None."""
    if not file_path.exists():
        return None
    try:
        backup_path = _compute_backup_path(file_path)
        shutil.copy2(str(file_path), str(backup_path))
        _cleanup_old_backups(file_path)
        return backup_path
    except (OSError, IOError) as e:
        _warn(f"Failed to create backup of {file_path}: {e}")
        return None


def _cleanup_old_backups(file_path: Path) -> None:
    """Remove backups older than BACKUP_RETENTION_SECONDS for the given file."""
    backup_dir = file_path.parent / BACKUP_DIR_NAME
    if not backup_dir.exists():
        return
    now = time.time()
    for bak in backup_dir.glob(f"{file_path.name}.*.bak"):
        try:
            if now - bak.stat().st_mtime > BACKUP_RETENTION_SECONDS:
                bak.unlink(missing_ok=True)
        except (OSError, IOError):
            pass


def _list_backups(file_path: Path) -> List[Path]:
    """List all available backups for the given file, sorted newest-first."""
    backup_dir = file_path.parent / BACKUP_DIR_NAME
    if not backup_dir.exists():
        return []
    backups = sorted(
        backup_dir.glob(f"{file_path.name}.*.bak"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return backups


def _compute_diff(old_content: str, new_content: str, file_path: str = "") -> str:
    """Generate a unified diff between old and new content."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )
    )
    return "\n".join(diff_lines)


def _prompt_user(message: str, default: str = "n") -> bool:
    """Prompt the user for yes/no approval. Returns True if approved."""
    prompt_suffix = " [y/N]: " if default == "n" else " [Y/n]: "
    try:
        response = input(message + prompt_suffix).strip().lower()
        if default == "n":
            return response in ("y", "yes")
        else:
            return response not in ("n", "no")
    except (EOFError, KeyboardInterrupt):
        return False


def _info(msg: str, json_mode: bool = False) -> None:
    """Print an info message."""
    if not json_mode:
        print(f"[INFO] {msg}", file=sys.stderr)


def _warn(msg: str, json_mode: bool = False) -> None:
    """Print a warning message."""
    if not json_mode:
        print(f"[WARN] {msg}", file=sys.stderr)


def _error(msg: str, json_mode: bool = False) -> None:
    """Print an error message."""
    if not json_mode:
        print(f"[ERROR] {msg}", file=sys.stderr, flush=True)


def _emit_json(data: Dict[str, Any]) -> None:
    """Emit a JSON result to stdout."""
    print(json.dumps(data, indent=2, default=str))


# ---------------------------------------------------------------------------
# Mass-edit detection
# ---------------------------------------------------------------------------

# Simple in-memory change tracker (persists for the lifetime of the process)
_change_log: List[Dict[str, Any]] = []


def _track_change(file_path: Path, action: str, approved: bool) -> None:
    """Record a file change for mass-edit detection."""
    _change_log.append({
        "path": str(file_path),
        "action": action,
        "approved": approved,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def _detect_mass_edit(window_seconds: int = 60) -> Tuple[bool, int]:
    """
    Detect if there's a mass-edit in progress within the given time window.
    Returns (is_mass_edit, count_of_recent_changes).
    """
    now = time.time()
    recent = [
        c for c in _change_log
        if c["approved"] and now - _parse_timestamp(c["timestamp"]) < window_seconds
    ]
    count = len(recent)
    return count >= MASS_EDIT_THRESHOLD, count


def _parse_timestamp(ts: str) -> float:
    """Parse an ISO timestamp string to a Unix timestamp."""
    try:
        dt = datetime.fromisoformat(ts)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Guard actions
# ---------------------------------------------------------------------------


def action_check(path: str, json_mode: bool = False) -> int:
    """Check if the given path is protected."""
    p = Path(path)
    protected = _is_protected(p)
    exists = p.exists()
    result = {
        "path": str(p.resolve()),
        "protected": protected,
        "exists": exists,
        "action": "check",
    }

    if json_mode:
        _emit_json(result)
    else:
        status = "PROTECTED" if protected else "not protected"
        print(f"{p} → {status}")
        if exists:
            print(f"  Size: {p.stat().st_size} bytes")
            print(f"  Modified: {datetime.fromtimestamp(p.stat().st_mtime).isoformat()}")

    return 0


def action_diff(path: str, new_content: Optional[str] = None, json_mode: bool = False) -> int:
    """Show diff between current file content and new content."""
    p = Path(path)

    if not p.exists():
        result = {
            "path": str(p.resolve()),
            "protected": _is_protected(p),
            "error": f"File does not exist: {path}",
            "action": "diff",
        }
        if json_mode:
            _emit_json(result)
        else:
            _error(result["error"], json_mode)
        return 1

    if not _is_protected(p):
        result = {
            "path": str(p.resolve()),
            "protected": False,
            "message": "File is not protected — no guard needed.",
            "action": "diff",
        }
        if json_mode:
            _emit_json(result)
        else:
            print("File is not protected — no guard needed.")
        return 0

    old_content = p.read_text(encoding="utf-8", errors="replace")

    if new_content is None:
        # Read from stdin if no content provided
        _info("Reading new content from stdin (Ctrl+D to end)...", json_mode)
        try:
            new_content = sys.stdin.read()
        except (EOFError, KeyboardInterrupt):
            _error("No input provided.", json_mode)
            return 1

    diff = _compute_diff(old_content, new_content, str(p))

    result: Dict[str, Any] = {
        "path": str(p.resolve()),
        "protected": True,
        "has_diff": bool(diff.strip()),
        "action": "diff",
    }

    if json_mode:
        result["diff"] = diff
        _emit_json(result)
    else:
        if diff.strip():
            print("Change diff:")
            print("-" * 60)
            print(diff)
            print("-" * 60)
        else:
            print("No differences — content is identical.")

    return 0


def action_protect(path: str, new_content: Optional[str] = None, force: bool = False,
                   json_mode: bool = False) -> int:
    """
    Protect a file from being overwritten.
    Shows diff, requires approval, creates backup before writing.
    """
    p = Path(path)
    protected = _is_protected(p)
    exists = p.exists()

    # If not protected, allow directly
    if not protected:
        if json_mode:
            _emit_json({
                "path": str(p.resolve()),
                "protected": False,
                "action": "protect",
                "status": "allowed",
                "message": "File is not protected — allowed.",
            })
        else:
            print("File is not protected — allowed.")
        return 0

    # Read new content
    if new_content is None:
        _info("Reading new content from stdin (Ctrl+D to end)...", json_mode)
        try:
            new_content = sys.stdin.read()
        except (EOFError, KeyboardInterrupt):
            _error("No input provided.", json_mode)
            return 1

    result: Dict[str, Any] = {
        "path": str(p.resolve()),
        "protected": True,
        "action": "protect",
    }

    # Show diff if file exists
    if exists:
        old_content = p.read_text(encoding="utf-8", errors="replace")
        diff = _compute_diff(old_content, new_content, str(p))

        if not diff.strip():
            if json_mode:
                result["status"] = "no_change"
                result["message"] = "Content is identical — nothing to do."
                _emit_json(result)
            else:
                print("Content is identical — nothing to do.")
            return 0

        result["diff"] = diff

        if json_mode:
            result["old_content"] = old_content
        else:
            print(f"\nProtected file: {p}")
            print("Proposed changes:")
            print("-" * 60)
            print(diff)
            print("-" * 60)
    else:
        if json_mode:
            result["new_content"] = new_content
        else:
            print(f"\nProtected file will be created: {p}")

    # Mass-edit detection
    is_mass_edit, recent_count = _detect_mass_edit()
    if is_mass_edit:
        result["mass_edit_detected"] = True
        result["recent_changes"] = recent_count
        msg = (
            f"\n⚠  MASS-EDIT DETECTED: {recent_count} protected files changed "
            f"in the last 60 seconds!"
        )
        if json_mode:
            pass  # embedded in result above
        else:
            print(msg)
            print()

    # Require approval
    if not force:
        approved = _prompt_user("Approve the change?", default="n")
        result["approved"] = approved

        if not approved:
            result["status"] = "denied"
            result["exit_code"] = 2
            if json_mode:
                _emit_json(result)
            else:
                print("\nOperation cancelled by user.")
            return 2
    else:
        result["approved"] = True
        result["force"] = True

    # Create backup
    if exists:
        backup_path = _create_backup(p)
        if backup_path:
            result["backup_path"] = str(backup_path)
            if not json_mode:
                print(f"Backup created: {backup_path}")
        else:
            # Failed backup — block overwrite
            result["status"] = "blocked_no_backup"
            result["error"] = "Could not create backup — blocked to protect data."
            if json_mode:
                _emit_json(result)
            else:
                _error("Could not create backup — blocked to protect data.", json_mode)
                print("To force without backup, pass --force.")
            return 1

    # Write the file
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(new_content, encoding="utf-8")
        _track_change(p, "write", approved=True)
        result["status"] = "written"
        result["exit_code"] = 0
        if json_mode:
            _emit_json(result)
        else:
            print(f"\n✓ File written: {p}")
    except (OSError, IOError) as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["exit_code"] = 1
        if json_mode:
            _emit_json(result)
        else:
            _error(f"Failed to write {p}: {e}", json_mode)
        return 1

    return 0


def action_delete(path: str, force: bool = False, json_mode: bool = False) -> int:
    """Guard against deleting protected files."""
    p = Path(path)
    protected = _is_protected(p)
    exists = p.exists()

    if not exists:
        result = {
            "path": str(p.resolve()),
            "protected": protected,
            "action": "delete",
            "error": "File does not exist.",
        }
        if json_mode:
            _emit_json(result)
        else:
            _error("File does not exist.", json_mode)
        return 1

    result: Dict[str, Any] = {
        "path": str(p.resolve()),
        "protected": protected,
        "action": "delete",
        "exists": True,
    }

    if not protected:
        if json_mode:
            result["status"] = "allowed"
            result["message"] = "File is not protected — allowed."
            _emit_json(result)
        else:
            print("File is not protected — allowed.")
        return 0

    # Show file info
    if not json_mode:
        size = p.stat().st_size
        mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
        print(f"\n⚠  PROTECTED FILE: {p}")
        print(f"   Size: {size} bytes")
        print(f"   Modified: {mtime}")
        print(f"   Action: DELETE")
        print()

    # Require approval
    if not force:
        approved = _prompt_user(
            f"Are you sure you want to DELETE protected file '{p.name}'?",
            default="n"
        )
        result["approved"] = approved

        if not approved:
            result["status"] = "denied"
            if json_mode:
                _emit_json(result)
            else:
                print("\nDeletion cancelled by user.")
            return 2
    else:
        result["approved"] = True
        result["force"] = True

    # Create backup before delete
    backup_path = _create_backup(p)
    if backup_path:
        result["backup_path"] = str(backup_path)
        if not json_mode:
            print(f"Backup created: {backup_path}")
    else:
        result["backup_path"] = None
        if not json_mode:
            print("(No backup created — file may be empty or backup failed)")

    # Perform deletion
    try:
        p.unlink()
        _track_change(p, "delete", approved=True)
        result["status"] = "deleted"
        if json_mode:
            _emit_json(result)
        else:
            print(f"\n✓ File deleted: {p}")
        return 0
    except (OSError, IOError) as e:
        result["status"] = "error"
        result["error"] = str(e)
        if json_mode:
            _emit_json(result)
        else:
            _error(f"Failed to delete {p}: {e}", json_mode)
        return 1


def action_rename(src: str, dst: str, force: bool = False, json_mode: bool = False) -> int:
    """Guard against renaming protected files."""
    src_path = Path(src)
    dst_path = Path(dst)
    protected_src = _is_protected(src_path)
    protected_dst = _is_protected(dst_path)

    if not src_path.exists():
        result = {
            "source": str(src_path.resolve()),
            "destination": str(dst_path.resolve()),
            "protected_source": protected_src,
            "action": "rename",
            "error": "Source file does not exist.",
        }
        if json_mode:
            _emit_json(result)
        else:
            _error("Source file does not exist.", json_mode)
        return 1

    result: Dict[str, Any] = {
        "source": str(src_path.resolve()),
        "destination": str(dst_path.resolve()),
        "protected_source": protected_src,
        "protected_destination": protected_dst,
        "action": "rename",
    }

    if not protected_src:
        if json_mode:
            result["message"] = "Source file is not protected — allowed."
            _emit_json(result)
        else:
            print("Source file is not protected — allowed.")
        return 0

    # Show info
    if not json_mode:
        size = src_path.stat().st_size
        print(f"\n⚠  PROTECTED FILE: {src_path}")
        print(f"   Size: {size} bytes")
        print(f"   Rename to: {dst_path}")
        print()

    # Require approval
    if not force:
        approved = _prompt_user(
            f"Are you sure you want to RENAME protected file '{src_path.name}' to '{dst_path.name}'?",
            default="n"
        )
        result["approved"] = approved

        if not approved:
            result["status"] = "denied"
            if json_mode:
                _emit_json(result)
            else:
                print("\nRename cancelled by user.")
            return 2
    else:
        result["approved"] = True
        result["force"] = True

    # Create backup of source before rename
    backup_path = _create_backup(src_path)
    if backup_path:
        result["backup_path"] = str(backup_path)
        if not json_mode:
            print(f"Backup created: {backup_path}")
    else:
        result["backup_path"] = None

    # Perform rename
    try:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        src_path.rename(dst_path)
        _track_change(src_path, "rename", approved=True)
        result["status"] = "renamed"
        if json_mode:
            _emit_json(result)
        else:
            print(f"\n✓ File renamed: {src_path} → {dst_path}")
        return 0
    except (OSError, IOError) as e:
        result["status"] = "error"
        result["error"] = str(e)
        if json_mode:
            _emit_json(result)
        else:
            _error(f"Failed to rename {src_path}: {e}", json_mode)
        return 1


def action_mass_check(paths: List[str], json_mode: bool = False) -> int:
    """Check multiple files at once for mass-edit detection."""
    results = []
    protected_count = 0
    for path in paths:
        p = Path(path)
        protected = _is_protected(p)
        if protected:
            protected_count += 1
        results.append({
            "path": str(p.resolve()),
            "protected": protected,
            "exists": p.exists(),
        })

    detected, recent_count = _detect_mass_edit()

    output = {
        "files_checked": len(paths),
        "protected_count": protected_count,
        "results": results,
        "mass_edit_detected": detected,
        "recent_changes": recent_count,
        "mass_edit_threshold": MASS_EDIT_THRESHOLD,
        "action": "mass_check",
    }

    if json_mode:
        _emit_json(output)
    else:
        print(f"Files checked: {len(paths)}")
        print(f"Protected files: {protected_count}")
        if detected:
            print(f"\n⚠  MASS-EDIT DETECTED: {recent_count} protected files changed recently!")
        else:
            print(f"Recent changes: {recent_count} (threshold: {MASS_EDIT_THRESHOLD})")
        print()
        for r in results:
            status = "PROTECTED" if r["protected"] else "OK"
            flag = " (exists)" if r["exists"] else " (not found)"
            print(f"  [{status}] {r['path']}{flag}")

    return 0


def action_backup(path: str, json_mode: bool = False) -> int:
    """Create a manual backup of a file."""
    p = Path(path)

    if not p.exists():
        result = {
            "path": str(p.resolve()),
            "action": "backup",
            "error": "File does not exist.",
        }
        if json_mode:
            _emit_json(result)
        else:
            _error("File does not exist.", json_mode)
        return 1

    backup_path = _create_backup(p)
    if backup_path:
        result = {
            "path": str(p.resolve()),
            "action": "backup",
            "backup_path": str(backup_path),
            "status": "created",
        }
        if json_mode:
            _emit_json(result)
        else:
            print(f"Backup created: {backup_path}")
        return 0
    else:
        result = {
            "path": str(p.resolve()),
            "action": "backup",
            "status": "failed",
            "error": "Could not create backup.",
        }
        if json_mode:
            _emit_json(result)
        else:
            _error("Could not create backup.", json_mode)
        return 1


def action_status(path: Optional[str] = None, json_mode: bool = False) -> int:
    """Show the status of protected files in a directory."""
    if path:
        base = Path(path)
    else:
        base = Path.cwd()

    if not base.exists():
        _error(f"Path does not exist: {base}", json_mode)
        return 1

    # Scan for files matching protected patterns
    protected_files = []
    # Walk depth-first but no more than 3 levels deep
    for root, dirs, files in os.walk(str(base)):
        rel_root = os.path.relpath(root, str(base))
        if rel_root == ".":
            rel_root = ""
        # Skip hidden dirs that aren't the root
        if rel_root and any(
            part.startswith(".") and part not in (".", "")
            for part in Path(rel_root).parts
        ):
            # Only skip if it's not .file_guard_backups (we want to show our own)
            if ".file_guard_backups" not in rel_root:
                continue

        depth = Path(rel_root).parts if rel_root else []
        if len(depth) > 2:
            # Still descend but mark as deeper
            pass

        for fname in files:
            fpath = os.path.join(root, fname)
            p = Path(fpath)
            if _is_protected(p):
                try:
                    stat = p.stat()
                    protected_files.append({
                        "path": str(p.resolve()),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "backups": len(_list_backups(p)),
                    })
                except (OSError, IOError):
                    protected_files.append({
                        "path": str(p.resolve()),
                        "size": 0,
                        "modified": None,
                        "backups": 0,
                    })

        # Limit scan depth
        current_depth = len(Path(rel_root).parts) if rel_root else 0
        if current_depth >= 2:
            dirs.clear()

    result = {
        "action": "status",
        "scanned_path": str(base.resolve()),
        "protected_files": protected_files,
        "total_protected": len(protected_files),
    }

    if json_mode:
        _emit_json(result)
    else:
        print(f"Protected file status for: {base.resolve()}")
        print(f"Total protected files found: {len(protected_files)}")
        print()
        if protected_files:
            for pf in protected_files:
                size_str = f"{pf['size']:,} bytes" if pf['size'] < 1024 else f"{pf['size']/1024:,.1f} KB" if pf['size'] < 1024**2 else f"{pf['size']/1024**2:,.1f} MB"
                backups = pf.get("backups", 0)
                backup_str = f", {backups} backup(s)" if backups else ""
                print(f"  {pf['path']} ({size_str}{backup_str})")
        else:
            print("  (none found)")

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build parser.
        """
    parser = argparse.ArgumentParser(
        prog="file_guard",
        description="Protect important files from accidental overwrite, deletion, or rename.",
        epilog=(
            "Exit codes: 0=success/safe, 1=blocked/error, 2=user denied\n\n"
            "Documentation: https://github.com/your-org/file-guard"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format instead of human-readable text.",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Skip user approval prompts (use with caution).",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # check
    p_check = subparsers.add_parser("check", help="Check if a file is protected")
    p_check.add_argument("path", help="Path to the file to check")

    # diff
    p_diff = subparsers.add_parser("diff", help="Show diff before modifying a protected file")
    p_diff.add_argument("path", help="Path to the protected file")
    p_diff.add_argument(
        "content", nargs="?", default=None,
        help="New content (optional; reads from stdin if omitted)",
    )

    # protect (write with guard)
    p_protect = subparsers.add_parser(
        "protect", help="Write to a file through the guard (shows diff, requires approval)"
    )
    p_protect.add_argument("path", help="Path to the file to write")
    p_protect.add_argument(
        "content", nargs="?", default=None,
        help="New content (optional; reads from stdin if omitted)",
    )

    # delete
    p_delete = subparsers.add_parser("delete", help="Delete a file with protection")
    p_delete.add_argument("path", help="Path to the file to delete")

    # rename
    p_rename = subparsers.add_parser("rename", help="Rename a file with protection")
    p_rename.add_argument("source", help="Source path")
    p_rename.add_argument("destination", help="Destination path")

    # mass-check
    p_mass = subparsers.add_parser(
        "mass-check", help="Check multiple files for mass-edit detection"
    )
    p_mass.add_argument("paths", nargs="+", help="Paths to check")

    # backup
    p_backup = subparsers.add_parser("backup", help="Create a manual backup of a file")
    p_backup.add_argument("path", help="Path to the file to back up")

    # status
    p_status = subparsers.add_parser(
        "status", help="Show protected file status in a directory"
    )
    p_status.add_argument(
        "path", nargs="?", default=None,
        help="Directory to scan (default: current working directory)",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point. Returns exit code (0, 1, or 2)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    json_mode = getattr(args, "json", False)
    force = getattr(args, "force", False)

    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == "check":
            return action_check(args.path, json_mode=json_mode)
        elif args.command == "diff":
            return action_diff(args.path, args.content, json_mode=json_mode)
        elif args.command == "protect":
            return action_protect(args.path, args.content, force=force, json_mode=json_mode)
        elif args.command == "delete":
            return action_delete(args.path, force=force, json_mode=json_mode)
        elif args.command == "rename":
            return action_rename(args.source, args.destination, force=force, json_mode=json_mode)
        elif args.command == "mass-check":
            return action_mass_check(args.paths, json_mode=json_mode)
        elif args.command == "backup":
            return action_backup(args.path, json_mode=json_mode)
        elif args.command == "status":
            return action_status(args.path, json_mode=json_mode)
        else:
            parser.print_help()
            return 0
    except KeyboardInterrupt:
        result = {"action": args.command, "status": "interrupted", "error": "User interrupted"}
        if json_mode:
            _emit_json(result)
        else:
            print("\nInterrupted.", file=sys.stderr)
        return 2
    except Exception as e:
        result = {"action": args.command, "status": "error", "error": str(e)}
        if json_mode:
            _emit_json(result)
        else:
            _error(f"Unexpected error: {e}")
        return 1


# ---------------------------------------------------------------------------
# Public API (for import)
# ---------------------------------------------------------------------------


def is_protected(path: Union[str, Path]) -> bool:
    """Check if a path is protected (public API)."""
    return _is_protected(path)


def guard_check(path: Union[str, Path]) -> Dict[str, Any]:
    """Check a file's protection status. Returns a dict result."""
    p = Path(path)
    return {
        "path": str(p.resolve()),
        "protected": _is_protected(p),
        "exists": p.exists(),
    }


def guard_diff(path: Union[str, Path], new_content: str) -> Dict[str, Any]:
    """Get a diff between current content and proposed content. Returns dict."""
    p = Path(path)
    result: Dict[str, Any] = {
        "path": str(p.resolve()),
        "protected": _is_protected(p),
    }
    if p.exists():
        old_content = p.read_text(encoding="utf-8", errors="replace")
        diff = _compute_diff(old_content, new_content, str(p))
        result["diff"] = diff
        result["has_diff"] = bool(diff.strip())
    else:
        result["diff"] = ""
        result["has_diff"] = False
        result["note"] = "File does not exist yet."
    return result


def guard_protect(path: Union[str, Path], new_content: str,
                  force: bool = False) -> Dict[str, Any]:
    """
    Write to a file through the guard. Returns dict with status.
    If not force, this will prompt on the terminal.
    """
    p = Path(path)
    result: Dict[str, Any] = {
        "path": str(p.resolve()),
        "protected": _is_protected(p),
        "action": "protect",
    }
    if not _is_protected(p):
        result["status"] = "allowed"
        result["message"] = "File is not protected."
        return result

    if p.exists():
        old_content = p.read_text(encoding="utf-8", errors="replace")
        diff = _compute_diff(old_content, new_content, str(p))
        result["diff"] = diff
        if not diff.strip():
            result["status"] = "no_change"
            return result
    else:
        result["diff"] = ""

    if not force:
        print("\n" + "=" * 60)
        print(f"Protected file: {p}")
        if result.get("diff"):
            print(result["diff"])
        print("=" * 60)
        approved = _prompt_user("Approve the change?")
        result["approved"] = approved
        if not approved:
            result["status"] = "denied"
            return result
    else:
        result["approved"] = True

    # Backup
    if p.exists():
        backup_path = _create_backup(p)
        if backup_path:
            result["backup_path"] = str(backup_path)
        else:
            result["status"] = "blocked_no_backup"
            result["error"] = "Could not create backup."
            return result

    # Write
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(new_content, encoding="utf-8")
        _track_change(p, "write", approved=True)
        result["status"] = "written"
    except (OSError, IOError) as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(main())
