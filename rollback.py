#!/usr/bin/env python3
"""
rollback.py — Rollback files using .bak backups.

Features:
  - Restore .bak backup files to their original names
  - List all available backups in a directory
  - Preview backup contents before restoring
  - Selective restore by filename or pattern
  - Safe rollback with confirmation

Gebruik:
    python rollback.py list <path>                      # Toon beschikbare backups
    python rollback.py restore <file.bak>               # Herstel een backup
    python rollback.py restore --from <dir> <orig_file> # Herstel van bak map
    python rollback.py restore --all <path>              # Herstel alle backups
    python rollback.py show <file.bak>                   # Toon backup inhoud
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


def find_backups(path: str) -> list[dict]:
    """Find all .bak backup files in a directory."""
    root = Path(path).resolve()
    backups = []

    if root.is_file():
        if root.suffix == ".bak":
            backups.append(parse_bak_file(root))
        return [b for b in backups if b]

    for dirpath, dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".bak"):
                fp = Path(dirpath) / fn
                backups.append(parse_bak_file(fp))

    # Sort by modification time (newest first)
    backups.sort(key=lambda x: x.get("mtime", ""), reverse=True)
    return backups


def parse_bak_file(filepath: Path) -> dict:
    """Parse a .bak file and return its metadata."""
    try:
        stat = filepath.stat()
        # Try to determine original filename
        bak_name = filepath.name
        orig_name = bak_name.replace(".bak", "")
        bak_dir = filepath.parent

        # If the original file also exists
        original_exists = (bak_dir / orig_name).exists()

        # Try to read first line as a quick preview
        preview = ""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                preview = f.readline().strip()[:80]
        except Exception:
            preview = "(binary)"

        return {
            "bak_file": str(filepath),
            "orig_file": str(bak_dir / orig_name),
            "bak_name": bak_name,
            "orig_name": orig_name,
            "directory": str(bak_dir),
            "size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "original_exists": original_exists,
            "preview": preview,
        }
    except Exception as e:
        return {
            "bak_file": str(filepath),
            "error": str(e),
        }


def restore_backup(bak_file: str, preview: bool = False) -> dict:
    """Restore a .bak file to its original name."""
    bak_path = Path(bak_file)
    if not bak_path.exists():
        return {"success": False, "error": f"Backup niet gevonden: {bak_file}"}

    orig_path = bak_path.with_suffix("")  # Remove .bak suffix

    if not bak_path.name.endswith(".bak"):
        return {"success": False, "error": f"Bestand is geen .bak: {bak_file}"}

    if preview:
        return {
            "success": True,
            "preview": True,
            "bak_file": str(bak_path),
            "orig_file": str(orig_path),
            "bak_size": bak_path.stat().st_size,
            "orig_exists": orig_path.exists(),
            "orig_size": orig_path.stat().st_size if orig_path.exists() else 0,
        }

    # Create backup of current file if it exists
    if orig_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safety_backup = orig_path.with_suffix(f".pre_rollback_{timestamp}")
        shutil.copy2(str(orig_path), str(safety_backup))

    # Restore
    try:
        shutil.copy2(str(bak_path), str(orig_path))
        return {
            "success": True,
            "bak_file": str(bak_path),
            "orig_file": str(orig_path),
            "bak_size": bak_path.stat().st_size,
            "safety_backup": str(safety_backup) if orig_path.exists() else None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def show_backup_content(bak_file: str, limit: int = 20) -> dict:
    """Show the content of a backup file."""
    bak_path = Path(bak_file)
    if not bak_path.exists():
        return {"success": False, "error": f"Backup niet gevonden: {bak_file}"}

    try:
        content = bak_path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")

        # Detect if binary
        if "\x00" in content[:1024]:
            return {
                "success": False,
                "error": "Binary file — kan inhoud niet tonen",
                "size": len(content),
            }

        return {
            "success": True,
            "file": str(bak_path),
            "orig_name": bak_path.with_suffix("").name,
            "total_lines": len(lines),
            "content": "\n".join(lines[:limit]),
            "truncated": len(lines) > limit,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def print_bak_list(backups: list[dict]) -> None:
    """Print a formatted list of available backups."""
    if not backups:
        print("\n Geen .bak backups gevonden")
        return

    print(f"\n{'='*60}")
    print(f" 🔄 BACKUP OVERZICHT — {len(backups)} backup(s)")
    print(f"{'='*60}")

    # Group by directory
    by_dir = {}
    for b in backups:
        by_dir.setdefault(b["directory"], []).append(b)

    for directory, dir_backups in sorted(by_dir.items()):
        print(f"\n ── {directory} ──")
        for b in dir_backups:
            status = "✅" if b["original_exists"] else "💀"
            size_kb = b["size"] / 1024 if b["size"] else 0
            print(f"   {status} {b['bak_name']}  ({size_kb:.1f} KB, {b.get('mtime', '?')[:19]})")
            print(f"       → {b['orig_name']}  |  Preview: {b.get('preview', '')[:60]}")

    print()


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="rollback.py — Rollback files using .bak backups",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python rollback.py list .                           # Toon alle backups
  python rollback.py restore script.py.bak            # Herstel backup
  python rollback.py restore --all .                  # Herstel alle backups
  python rollback.py restore --preview script.py.bak  # Preview restore
  python rollback.py show script.py.bak               # Toon backup inhoud
        """,
    )
    parser.add_argument("action", choices=["list", "restore", "show"],
                        help="list: toon backups, restore: herstel, show: toon inhoud")
    parser.add_argument("target", nargs="?", help="Bestand, .bak bestand of directory")
    parser.add_argument("--all", "-a", action="store_true",
                        help="Herstel alle backups in een directory")
    parser.add_argument("--from", "-f", metavar="DIR", dest="from_dir",
                        help="Directory met de backups")
    parser.add_argument("--preview", "-p", action="store_true",
                        help="Preview alleen (niet herstellen)")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--limit", "-l", type=int, default=20,
                        help="Max regels voor show (default: 20)")
    parser.add_argument("--confirm", "-c", action="store_true",
                        help="Automatisch bevestigen (geen prompt)")
    parser.add_argument("--version", action="version", version="rollback.py v1.0.0")

    args = parser.parse_args()

    if args.action == "list":
        path = args.target or "."
        target = Path(path).resolve()
        if not target.exists():
            print(f" ❌ '{path}' bestaat niet", file=sys.stderr)
            sys.exit(1)

        backups = find_backups(str(target))

        if args.json:
            print(json.dumps(backups, indent=2, ensure_ascii=False))
        else:
            print_bak_list(backups)

    elif args.action == "restore":
        if not args.target and not args.from_dir:
            print(" ❌ Geef een .bak bestand of --from DIR + bestandsnaam", file=sys.stderr)
            sys.exit(1)

        if args.all:
            path = args.target or "."
            target = Path(path).resolve()
            if not target.exists():
                print(f" ❌ '{path}' bestaat niet", file=sys.stderr)
                sys.exit(1)

            backups = find_backups(str(target))
            if not backups:
                print(" Geen .bak backups gevonden")
                return

            results = []
            for b in backups:
                result = restore_backup(b["bak_file"], args.preview)
                results.append(result)

            if args.json:
                print(json.dumps(results, indent=2, ensure_ascii=False))
            else:
                success = sum(1 for r in results if r["success"])
                failed = sum(1 for r in results if not r["success"])
                print(f"\n{'='*60}")
                print(f" 🔄 ROLLBACK — ALLE BACKUPS")
                print(f"{'='*60}")
                print(f"   ✅ Hersteld: {success}")
                print(f"   ❌ Mislukt:  {failed}")
                for r in results:
                    if r["success"] and not r.get("preview"):
                        print(f"   ✅ {r['orig_file']} (van {r['bak_file']})")
                    elif r["success"] and r.get("preview"):
                        print(f"   👁  Preview: {r['bak_file']} → {r['orig_file']}")
                    else:
                        print(f"   ❌ {r.get('bak_file', '?')}: {r.get('error', '?')}")
            return

        # Single file restore
        if args.from_dir:
            bak_path = Path(args.from_dir) / f"{args.target}.bak"
        else:
            bak_path = Path(args.target).resolve()

        if not bak_path.exists() and not bak_path.name.endswith(".bak"):
            bak_path = bak_path.with_suffix(".bak")

        if not bak_path.exists():
            print(f" ❌ Backup niet gevonden: {bak_path}", file=sys.stderr)
            sys.exit(1)

        if not args.confirm and not args.preview:
            orig = bak_path.with_suffix("")
            print(f"\n Weet je zeker dat je {bak_path} wilt herstellen naar {orig}?")
            print(f" Dit overschrijft {orig} als het bestaat.")
            resp = input(" Doorgaan? (y/N): ").strip().lower()
            if resp != "y":
                print(" Geannuleerd.")
                sys.exit(0)

        result = restore_backup(str(bak_path), args.preview)

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            if result["success"]:
                if result.get("preview"):
                    print(f"\n 👁  Preview restore:")
                    print(f"    Backup:  {result['bak_file']} ({result['bak_size']} bytes)")
                    print(f"    Origineel: {result['orig_file']}")
                    print(f"    Bestaat al: {'Ja' if result['orig_exists'] else 'Nee'}")
                else:
                    print(f"\n ✅ Hersteld: {result['bak_file']} → {result['orig_file']}")
                    if result.get("safety_backup"):
                        print(f"    🛡  Safety backup: {result['safety_backup']}")
            else:
                print(f"\n ❌ Fout: {result.get('error', 'Onbekende fout')}")

    elif args.action == "show":
        if not args.target:
            print(" ❌ Geef een .bak bestand om te tonen", file=sys.stderr)
            sys.exit(1)

        bak_path = Path(args.target).resolve()
        if not bak_path.exists():
            print(f" ❌ '{args.target}' bestaat niet", file=sys.stderr)
            sys.exit(1)

        result = show_backup_content(str(bak_path), args.limit)

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            if result["success"]:
                print(f"\n{'='*60}")
                print(f" 📄 BACKUP INHOUD — {result['file']}")
                print(f"   Origineel: {result['orig_name']}")
                print(f"   Totaal: {result['total_lines']} regels")
                print(f"{'='*60}")
                print(result["content"])
                if result["truncated"]:
                    print(f"\n   ... ({result['total_lines'] - args.limit} regels verborgen)")
                    print(f"   Gebruik --limit N om meer te tonen")
            else:
                print(f" ❌ {result.get('error', 'Onbekende fout')}")


if __name__ == "__main__":
    main()
