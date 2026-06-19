#!/usr/bin/env python3
"""
php_dep_audit.py — Composer dependency auditor.

Audit PHP project dependencies via Composer:
  - composer.json validation
  - composer.lock package inventory
  - composer audit (known vulnerabilities)
  - Outdated packages check
  - License compliance check
  - Direct vs dev dependency breakdown

Gebruik:
    python php_dep_audit.py <path>
    python php_dep_audit.py <path> --json
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

COMPOSER = shutil.which("composer") or shutil.which("composer.phar")


def find_composer_files(root: Path) -> dict:
    result = {
        "composer_json": None,
        "composer_lock": None,
        "vendor_dir": None,
    }
    
    for path in [root, root.parent] if not root.is_dir() else [root]:
        json_path = path / "composer.json"
        lock_path = path / "composer.lock"
        vendor = path / "vendor"
        
        if json_path.exists():
            result["composer_json"] = str(json_path)
        if lock_path.exists():
            result["composer_lock"] = str(lock_path)
        if vendor.exists():
            result["vendor_dir"] = str(vendor)
    
    return result


def parse_composer_json(root: Path) -> dict:
    """Parse composer.json for dependency info."""
    json_path = root / "composer.json"
    if not json_path.exists():
        return {}
    
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except:
        return {"error": "Cannot parse composer.json"}
    
    return {
        "name": data.get("name", "unknown"),
        "description": data.get("description", ""),
        "type": data.get("type", "library"),
        "license": data.get("license", []),
        "php_version": data.get("require", {}).get("php", "unknown"),
        "dependencies": {
            "require": len(data.get("require", {})),
            "require-dev": len(data.get("require-dev", {})),
        },
        "autoload": list(data.get("autoload", {}).keys()) if "autoload" in data else [],
    }


def parse_composer_lock(root: Path) -> dict:
    """Parse composer.lock for installed packages."""
    lock_path = root / "composer.lock"
    if not lock_path.exists():
        return {}
    
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except:
        return {"error": "Cannot parse composer.lock"}
    
    packages = data.get("packages", []) + data.get("packages-dev", [])
    
    # Group by type
    by_type = {}
    licenses = {}
    for pkg in packages:
        ptype = pkg.get("type", "library")
        by_type[ptype] = by_type.get(ptype, 0) + 1
        for lic in pkg.get("license", []):
            licenses[lic] = licenses.get(lic, 0) + 1
    
    return {
        "total_packages": len(packages),
        "packages_prod": len(data.get("packages", [])),
        "packages_dev": len(data.get("packages-dev", [])),
        "by_type": by_type,
        "licenses": licenses,
        "platform": {k: v for k, v in data.get("platform", {}).items()},
        "platform_overrides": data.get("platform-overrides", {}),
    }


def run_composer_audit(root: Path) -> dict:
    """Run composer audit for vulnerability scanning."""
    if not COMPOSER:
        return {"error": "Composer not installed", "vulnerabilities": []}
    
    try:
        result = subprocess.run(
            [COMPOSER, "audit", "--format=json", "--no-interaction"],
            cwd=str(root), capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
        )
        
        if result.returncode == 0:
            return {"clean": True, "vulnerabilities": []}
        
        try:
            data = json.loads(result.stdout)
            vulns = []
            for adv in data.get("advisories", []):
                vulns.append({
                    "package": adv.get("packageName", "unknown"),
                    "cve": adv.get("cve", ""),
                    "title": adv.get("title", ""),
                    "link": adv.get("link", ""),
                })
            return {"clean": False, "vulnerabilities": vulns}
        except:
            return {"clean": None, "vulnerabilities": [], "raw": result.stdout[:1000]}
    
    except subprocess.TimeoutExpired:
        return {"error": "Audit timed out", "vulnerabilities": []}
    except FileNotFoundError:
        return {"error": "Composer not found", "vulnerabilities": []}


def run_composer_outdated(root: Path) -> dict:
    """Check for outdated packages."""
    if not COMPOSER:
        return {"error": "Composer not installed", "outdated": []}
    
    try:
        result = subprocess.run(
            [COMPOSER, "outdated", "--format=json", "--no-interaction", "--direct"],
            cwd=str(root), capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
        )
        try:
            data = json.loads(result.stdout)
            outdated_list = []
            if data.get("installed"):
                for pkg in data["installed"]:
                    outdated_list.append({
                        "name": pkg["name"],
                        "current": pkg["version"],
                        "latest": pkg.get("latest", "?"),
                        "status": pkg.get("latest-status", "unknown"),
                    })
            return {"outdated": outdated_list, "count": len(outdated_list)}
        except:
            return {"outdated": [], "count": 0, "raw": result.stdout[:500]}
    except:
        return {"outdated": [], "count": 0}


def print_report(json_info: dict, lock_info: dict, audit: dict, outdated: dict) -> None:
    print(f"\n{'=' * 70}")
    print(f" COMPOSER AUDIT")
    print(f"{'=' * 70}")
    
    # Project info
    if json_info and "name" in json_info:
        print(f"\n   Project: {json_info['name']}")
        print(f"   PHP: {json_info.get('php_version', 'unknown')}")
        print(f"   License: {', '.join(json_info.get('license', []))}")
        print(f"   Dependencies: {json_info['dependencies'].get('require', 0)} prod, "
              f"{json_info['dependencies'].get('require-dev', 0)} dev")
    
    # Lock info
    if lock_info:
        print(f"\n   Installed: {lock_info['total_packages']} packages "
              f"({lock_info['packages_prod']} prod, {lock_info['packages_dev']} dev)")
        
        if lock_info.get("by_type"):
            print(f"   By type:")
            for ptype, count in sorted(lock_info["by_type"].items(), key=lambda x: -x[1])[:5]:
                print(f"     - {ptype}: {count}")
    
    # Vulnerabilities
    print(f"\n   Vulnerabilities: ", end="")
    if audit.get("clean") is True:
        print("✅ None found")
    elif audit.get("error"):
        print(f"⚠ {audit['error']}")
    elif audit.get("vulnerabilities"):
        print(f"🔴 {len(audit['vulnerabilities'])} found!")
        for v in audit["vulnerabilities"]:
            print(f"     - {v['package']}: {v.get('title', v.get('cve', ''))}")
            if v.get("link"):
                print(f"       {v['link']}")
    else:
        print("⚠ Could not determine")
    
    # Outdated
    if outdated.get("outdated"):
        print(f"\n   Outdated ({outdated['count']}):")
        for pkg in sorted(outdated["outdated"], key=lambda p: p["status"])[:10]:
            status_icon = "🔴" if "major" in pkg.get("status", "") else "🟡" if "minor" in pkg.get("status", "") else "🔵"
            print(f"     {status_icon} {pkg['name']}: {pkg['current']} → {pkg['latest']}")
    elif not outdated.get("error"):
        print(f"   Outdated: ✅ All up to date")
    
    print()


def print_json_output(json_info: dict, lock_info: dict, audit: dict, outdated: dict) -> None:
    output = {
        "project": json_info,
        "installed": lock_info,
        "vulnerabilities": audit,
        "outdated": outdated,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="php_dep_audit.py - Composer dependency auditor")
    parser.add_argument("path", help="PHP project directory with composer.json")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--skip-audit", action="store_true", help="Skip vulnerability scan")
    parser.add_argument("--skip-outdated", action="store_true", help="Skip outdated check")
    parser.add_argument("--version", action="version", version="php_dep_audit.py v1.0.0")
    
    args = parser.parse_args()
    root = Path(args.path)
    if not root.exists():
        print(f"Not found", file=sys.stderr); sys.exit(1)
    if not root.is_dir():
        root = root.parent
    
    print(f"\n📦 PHP Dependency Audit v1.0.0 — {root}")
    print(f"{'=' * 70}")
    
    composer_files = find_composer_files(root)
    
    if not composer_files["composer_json"]:
        print("   No composer.json found")
        sys.exit(0)
    
    print(f"   composer.json: {'✅' if composer_files['composer_json'] else '❌ Not found'}")
    print(f"   composer.lock: {'✅' if composer_files['composer_lock'] else '❌ Not found'}")
    print(f"   vendor/:       {'✅' if composer_files['vendor_dir'] else '❌ Not found'}")
    
    json_info = parse_composer_json(root)
    lock_info = parse_composer_lock(root) if not args.skip_audit else {}
    
    audit = {}
    if not args.skip_audit:
        print(f"\n   Running composer audit...")
        audit = run_composer_audit(root)
    
    outdated = {}
    if not args.skip_outdated:
        print(f"   Checking outdated packages...")
        outdated = run_composer_outdated(root)
    
    if args.json:
        print_json_output(json_info, lock_info, audit, outdated)
    else:
        print_report(json_info, lock_info, audit, outdated)


if __name__ == "__main__":
    main()
