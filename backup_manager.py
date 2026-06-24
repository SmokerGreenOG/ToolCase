#!/usr/bin/env python3
"""
backup_manager.py — Create, list, diff, restore, and prune timestamped snapshots.

Manages file/directory snapshots stored under .backups/YYYY-MM-DD-HHMMSS/.

Actions:
  snapshot <file|dir>     Create timestamped snapshot in .backups/YYYY-MM-DD-HHMMSS/
  list [path]             List all backups, or snapshots for a specific path
  diff <snapshot_id> [file]   Compare snapshot with current version
  restore <snapshot_id>       Restore entire snapshot
  restore-file <snapshot_id> <file>  Restore a single file from snapshot
  prune [keep=N]              Remove old backups, keep N most recent (default 5)

Usage:
    python backup_manager.py snapshot <path>
    python backup_manager.py list
    python backup_manager.py list <path>
    python backup_manager.py diff 2026-06-10-120000
    python backup_manager.py diff 2026-06-10-120000 some_file.py
    python backup_manager.py restore 2026-06-10-120000
    python backup_manager.py restore-file 2026-06-10-120000 some_file.py
    python backup_manager.py prune --keep 3
    python backup_manager.py --help
    python backup_manager.py snapshot <path> --json
"""

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import difflib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_ISSUES = 1
EXIT_ERROR = 2

BACKUP_DIR_NAME = ".backups"
SNAPSHOT_ID_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{6}$")

# How many recent snapshots to keep by default
DEFAULT_KEEP = 5


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def backup_root(base: Path) -> Path:
    """Return the .backups directory path anchored to *base*."""
    return base / BACKUP_DIR_NAME


def snapshot_dir(base: Path, snapshot_id: str) -> Path:
    """Return the directory for a specific snapshot."""
    return backup_root(base) / snapshot_id


# ---------------------------------------------------------------------------
# Snapshot naming
# ---------------------------------------------------------------------------


def generate_snapshot_id() -> str:
    """Generate a snapshot ID like 2026-06-10-181229."""
    return datetime.now().strftime("%Y-%m-%d-%H%M%S")


# ---------------------------------------------------------------------------
# Snapshot — create
# ---------------------------------------------------------------------------


def do_snapshot(base: Path, target: str, *, json_out: bool) -> int:
    """Create a snapshot of *target* under .backups/<snapshot_id>/."""
    src = Path(target).resolve()

    if not src.exists():
        msg = f"error: path does not exist: {src}"
        if json_out:
            print(json.dumps({"status": "error", "message": msg}))
        else:
            print(msg)
        return EXIT_ERROR

    snap_id = generate_snapshot_id()
    dest = snapshot_dir(base, snap_id)
    dest.mkdir(parents=True, exist_ok=True)

    # Resolve the relative path from base to target for storage key
    try:
        rel = src.relative_to(base)
    except ValueError:
        # Target is outside base — store by absolute path stem as name
        rel = Path(src.name)

    dest_path = dest / rel

    try:
        if src.is_dir():
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dest_path, dirs_exist_ok=True)
        else:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest_path)
    except Exception as exc:
        msg = f"error: snapshot failed for {src}: {exc}"
        if json_out:
            print(json.dumps({"status": "error", "message": msg}))
        else:
            print(msg)
        return EXIT_ERROR

    # Also backup any existing file at target location BEFORE modifying
    # (this snapshot itself is the backup)

    result = {
        "status": "ok",
        "action": "snapshot",
        "snapshot_id": snap_id,
        "source": str(src),
        "stored_at": str(dest_path),
    }

    if json_out:
        print(json.dumps(result))
    else:
        print(f"snapshot created: {snap_id}")
        print(f"  source:    {src}")
        print(f"  stored at: {dest_path}")

    return EXIT_OK


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def do_list(base: Path, target: str | None, *, json_out: bool) -> int:
    """List all snapshots, or snapshots for a specific path."""
    bdir = backup_root(base)

    if not bdir.is_dir():
        if json_out:
            print(json.dumps({"status": "ok", "snapshots": []}))
        else:
            print("no backups found")
        return EXIT_OK

    # Collect all snapshot dirs, sorted newest first
    snap_dirs: list[Path] = sorted(
        [d for d in bdir.iterdir() if d.is_dir() and SNAPSHOT_ID_PATTERN.match(d.name)],
        reverse=True,
    )

    if not snap_dirs:
        if json_out:
            print(json.dumps({"status": "ok", "snapshots": []}))
        else:
            print("no backups found")
        return EXIT_OK

    if target is None:
        # List all snapshots
        entries = []
        for sd in snap_dirs:
            snap_id = sd.name
            # Count files/dirs inside
            contents = list(sd.rglob("*"))
            total_files = sum(1 for p in contents if p.is_file())
            total_dirs = sum(1 for p in contents if p.is_dir())
            entries.append({
                "snapshot_id": snap_id,
                "total_files": total_files,
                "total_dirs": total_dirs,
            })

        if json_out:
            print(json.dumps({"status": "ok", "snapshots": entries}))
        else:
            print(f"snapshots in {bdir}/")
            print(f"{'snapshot_id':<22} {'files':<8} {'dirs':<6}")
            print("-" * 40)
            for e in entries:
                print(f"{e['snapshot_id']:<22} {e['total_files']:<8} {e['total_dirs']:<6}")

    else:
        # List snapshots containing a specific path
        target_path = Path(target).resolve()
        try:
            rel = target_path.relative_to(base)
        except ValueError:
            rel = Path(target_path.name)

        entries = []
        for sd in snap_dirs:
            candidate = sd / rel
            if candidate.exists():
                total_files = 0
                total_dirs = 0
                if candidate.is_dir():
                    contents = list(candidate.rglob("*"))
                    total_files = sum(1 for p in contents if p.is_file())
                    total_dirs = sum(1 for p in contents if p.is_dir())
                else:
                    total_files = 1
                entries.append({
                    "snapshot_id": sd.name,
                    "total_files": total_files,
                    "total_dirs": total_dirs,
                })

        if json_out:
            print(json.dumps({"status": "ok", "target": str(target_path), "snapshots": entries}))
        else:
            if not entries:
                print(f"no snapshots found for: {target_path}")
            else:
                print(f"snapshots for {target_path}:")
                print(f"{'snapshot_id':<22} {'files':<8} {'dirs':<6}")
                print("-" * 40)
                for e in entries:
                    print(f"{e['snapshot_id']:<22} {e['total_files']:<8} {e['total_dirs']:<6}")

    return EXIT_OK


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def do_diff(base: Path, snapshot_id: str, file_path: str | None, *, json_out: bool) -> int:
    """Compare a snapshot against the current version."""
    sd = snapshot_dir(base, snapshot_id)

    if not sd.is_dir():
        msg = f"error: snapshot not found: {snapshot_id}"
        if json_out:
            print(json.dumps({"status": "error", "message": msg}))
        else:
            print(msg)
        return EXIT_ERROR

    if file_path:
        # Diff a single file within the snapshot
        target = Path(file_path).resolve()
        try:
            rel = target.relative_to(base)
        except ValueError:
            rel = Path(target.name)

        snapshot_file = sd / rel

        if not snapshot_file.is_file():
            msg = f"error: file not found in snapshot: {file_path}"
            if json_out:
                print(json.dumps({"status": "error", "message": msg}))
            else:
                print(msg)
            return EXIT_ERROR

        return _diff_files(target, snapshot_file, json_out=json_out)
    else:
        # Diff everything in the snapshot
        all_snapshot_files = sorted(sd.rglob("*"))
        diffs = []

        for sp in all_snapshot_files:
            if not sp.is_file():
                continue

            try:
                rel = sp.relative_to(sd)
            except ValueError:
                continue

            current_file = base / rel

            if not current_file.exists():
                diffs.append({
                    "file": str(rel),
                    "status": "deleted",
                    "diff": None,
                })
                continue

            file_diff = _compute_diff(current_file, sp)
            if file_diff:
                diffs.append({
                    "file": str(rel),
                    "status": "modified",
                    "diff": file_diff,
                })

        # Also check for new files that don't exist in snapshot
        # (we only report what's in the snapshot vs current)

        if json_out:
            print(json.dumps({"status": "ok", "snapshot_id": snapshot_id, "diffs": diffs}))
        else:
            if not diffs:
                print(f"no differences for snapshot {snapshot_id}")
            else:
                print(f"differences for snapshot {snapshot_id}:")
                for d in diffs:
                    print(f"\n--- {d['file']} ({d['status']})")
                    if d["diff"]:
                        print(d["diff"])
        return EXIT_OK


def _diff_files(current: Path, snapshot: Path, *, json_out: bool) -> int:
    """Diff a single current file against its snapshot version."""
    diff = _compute_diff(current, snapshot)

    if json_out:
        print(json.dumps({
            "status": "ok",
            "file": str(current),
            "diff": diff,
        }))
    else:
        if diff:
            print(f"diff for {current}:")
            print(diff)
        else:
            print(f"no differences: {current}")

    return EXIT_OK if diff is None else EXIT_ISSUES


def _compute_diff(current: Path, snapshot: Path) -> str | None:
    """Return unified diff string, or None if files are identical."""
    try:
        cur_text = current.read_text(encoding="utf-8", errors="replace")
    except Exception:
        cur_text = ""

    try:
        snap_text = snapshot.read_text(encoding="utf-8", errors="replace")
    except Exception:
        snap_text = ""

    if cur_text == snap_text:
        return None

    diff_lines = list(
        difflib.unified_diff(
            snap_text.splitlines(keepends=True),
            cur_text.splitlines(keepends=True),
            fromfile=f"snapshot/{current.name}",
            tofile=f"current/{current.name}",
        )
    )

    return "".join(diff_lines) if diff_lines else None


# ---------------------------------------------------------------------------
# Restore — full snapshot
# ---------------------------------------------------------------------------


def do_restore(base: Path, snapshot_id: str, *, json_out: bool) -> int:
    """Restore an entire snapshot, overwriting current files."""
    sd = snapshot_dir(base, snapshot_id)

    if not sd.is_dir():
        msg = f"error: snapshot not found: {snapshot_id}"
        if json_out:
            print(json.dumps({"status": "error", "message": msg}))
        else:
            print(msg)
        return EXIT_ERROR

    all_files = sorted(sd.rglob("*"))
    restored = []
    errors = []

    for sp in all_files:
        if not sp.is_file():
            continue

        try:
            rel = sp.relative_to(sd)
        except ValueError:
            continue

        dest = base / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Backup existing file before overwriting (create a snapshot of it)
            # We don't re-snapshot here to avoid infinite recursion, but we
            # do make a .bak copy
            if dest.exists():
                bak = dest.with_suffix(dest.suffix + ".bak")
                shutil.copy2(dest, bak)

            shutil.copy2(sp, dest)
            restored.append(str(rel))
        except Exception as exc:
            errors.append({"file": str(rel), "error": str(exc)})

    result = {
        "status": "ok" if not errors else "partial",
        "snapshot_id": snapshot_id,
        "restored": restored,
        "errors": errors,
    }

    if json_out:
        print(json.dumps(result))
    else:
        print(f"restored snapshot {snapshot_id}: {len(restored)} files")
        if errors:
            print("errors:")
            for e in errors:
                print(f"  {e['file']}: {e['error']}")

    return EXIT_OK if not errors else EXIT_ERROR


# ---------------------------------------------------------------------------
# Restore — single file
# ---------------------------------------------------------------------------


def do_restore_file(base: Path, snapshot_id: str, file_path: str, *, json_out: bool) -> int:
    """Restore a single file from a snapshot."""
    sd = snapshot_dir(base, snapshot_id)

    if not sd.is_dir():
        msg = f"error: snapshot not found: {snapshot_id}"
        if json_out:
            print(json.dumps({"status": "error", "message": msg}))
        else:
            print(msg)
        return EXIT_ERROR

    target = Path(file_path).resolve()
    try:
        rel = target.relative_to(base)
    except ValueError:
        rel = Path(target.name)

    snapshot_file = sd / rel

    if not snapshot_file.is_file():
        msg = f"error: file not found in snapshot: {file_path}"
        if json_out:
            print(json.dumps({"status": "error", "message": msg}))
        else:
            print(msg)
        return EXIT_ERROR

    try:
        # Backup existing file before overwriting
        if target.exists():
            bak = target.with_suffix(target.suffix + ".bak")
            shutil.copy2(target, bak)

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot_file, target)

        result = {
            "status": "ok",
            "snapshot_id": snapshot_id,
            "file": str(target),
        }

        if json_out:
            print(json.dumps(result))
        else:
            print(f"restored {target} from snapshot {snapshot_id}")

        return EXIT_OK

    except Exception as exc:
        msg = f"error: restore failed for {target}: {exc}"
        if json_out:
            print(json.dumps({"status": "error", "message": msg}))
        else:
            print(msg)
        return EXIT_ERROR


# ---------------------------------------------------------------------------
# Prune
# ---------------------------------------------------------------------------


def do_prune(base: Path, keep: int, *, json_out: bool) -> int:
    """Remove old snapshots, keeping the N most recent."""
    bdir = backup_root(base)

    if not bdir.is_dir():
        if json_out:
            print(json.dumps({"status": "ok", "pruned": [], "kept": 0}))
        else:
            print("no backups to prune")
        return EXIT_OK

    snap_dirs: list[Path] = sorted(
        [d for d in bdir.iterdir() if d.is_dir() and SNAPSHOT_ID_PATTERN.match(d.name)],
        reverse=True,  # newest first
    )

    if len(snap_dirs) <= keep:
        if json_out:
            print(json.dumps({"status": "ok", "pruned": [], "kept": len(snap_dirs)}))
        else:
            print(f"nothing to prune ({len(snap_dirs)} snapshots, keep={keep})")
        return EXIT_OK

    to_prune = snap_dirs[keep:]  # oldest beyond keep count
    pruned_ids = []

    for sd in to_prune:
        try:
            shutil.rmtree(sd)
            pruned_ids.append(sd.name)
        except Exception as exc:
            msg = f"error: failed to prune {sd.name}: {exc}"
            if json_out:
                print(json.dumps({"status": "error", "message": msg}))
            else:
                print(msg)
            return EXIT_ERROR

    result = {
        "status": "ok",
        "pruned": pruned_ids,
        "kept": len(snap_dirs) - len(pruned_ids),
    }

    if json_out:
        print(json.dumps(result))
    else:
        print(f"pruned {len(pruned_ids)} old snapshots, kept {result['kept']}")

    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build parser.
        """
    parser = argparse.ArgumentParser(
        description="Create, list, diff, restore, and prune timestamped snapshots.",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON.",
    )

    sub = parser.add_subparsers(dest="action", required=True)

    # snapshot
    snap = sub.add_parser("snapshot", help="Create a timestamped snapshot.")
    snap.add_argument("path", help="File or directory to snapshot.")

    # list
    lst = sub.add_parser("list", help="List all backups or snapshots for a path.")
    lst.add_argument("path", nargs="?", help="Optional path to filter snapshots.")

    # diff
    diff = sub.add_parser("diff", help="Compare snapshot with current version.")
    diff.add_argument("snapshot_id", help="Snapshot ID (YYYY-MM-DD-HHMMSS).")
    diff.add_argument("file", nargs="?", help="Optional specific file to diff.")

    # restore
    res = sub.add_parser("restore", help="Restore entire snapshot.")
    res.add_argument("snapshot_id", help="Snapshot ID (YYYY-MM-DD-HHMMSS).")

    # restore-file
    rf = sub.add_parser("restore-file", help="Restore a single file from snapshot.")
    rf.add_argument("snapshot_id", help="Snapshot ID (YYYY-MM-DD-HHMMSS).")
    rf.add_argument("file", help="File to restore.")

    # prune
    prn = sub.add_parser("prune", help="Remove old backups, keeping N most recent.")
    prn.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_KEEP,
        help=f"Number of recent snapshots to keep (default: {DEFAULT_KEEP}).",
    )

    return parser


def main() -> int:
    """main.
        """
    parser = build_parser()
    args = parser.parse_args()

    base = Path.cwd()

    # Validate snapshot_id format where applicable
    if hasattr(args, "snapshot_id"):
        if not SNAPSHOT_ID_PATTERN.match(args.snapshot_id):
            print(f"error: invalid snapshot ID format: {args.snapshot_id}")
            print("       expected format: YYYY-MM-DD-HHMMSS")
            return EXIT_ERROR

    match args.action:
        case "snapshot":
            return do_snapshot(base, args.path, json_out=args.json)
        case "list":
            return do_list(base, args.path, json_out=args.json)
        case "diff":
            return do_diff(base, args.snapshot_id, args.file, json_out=args.json)
        case "restore":
            return do_restore(base, args.snapshot_id, json_out=args.json)
        case "restore-file":
            return do_restore_file(base, args.snapshot_id, args.file, json_out=args.json)
        case "prune":
            return do_prune(base, args.keep, json_out=args.json)
        case _:
            parser.print_help()
            return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
# new comment
