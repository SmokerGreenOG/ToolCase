#!/usr/bin/env python3
"""
php_version_audit.py — PHP version compatibility checker.

Detecteert deprecated en removed functies/features per PHP versie (5.x → 8.x):
  - Removed functies per versie
  - Deprecated functies met suggested replacements
  - Incompatible syntax changes
  - Extensions die verwijderd zijn

Gebruik:
    python php_version_audit.py <path> --target 8.1
    python php_version_audit.py <path> --target 8.2 --json
"""

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

EXCLUDE_DIRS = {
    "node_modules",
    "vendor",
    ".git",
    "__pycache__",
    "tests/fixtures",
    ".venv",
    "venv",
    "dist",
    "build",
    ".cache",
}

# Deprecated/removed functions per version
DEPRECATED = {
    "7.0": {
        "removed": [
            ("mysql_connect", "Use PDO or MySQLi"),
            ("mysql_db_query", "Use PDO::query()"),
            ("mysql_escape_string", "Use PDO::quote() or prepared statements"),
            ("mysql_fetch_array", "Use PDOStatement::fetch()"),
            ("mysql_fetch_assoc", "Use PDOStatement::fetch(PDO::FETCH_ASSOC)"),
            ("mysql_fetch_row", "Use PDOStatement::fetch(PDO::FETCH_NUM)"),
            ("mysql_free_result", "Not needed with PDO"),
            ("mysql_get_client_info", "Use PDO::getAttribute()"),
            ("mysql_get_host_info", "Use PDO"),
            ("mysql_get_proto_info", "Use PDO"),
            ("mysql_get_server_info", "Use PDO::getAttribute(PDO::ATTR_SERVER_VERSION)"),
            ("mysql_info", "Use PDO"),
            ("mysql_list_dbs", "Use SHOW DATABASES via PDO"),
            ("mysql_list_fields", "Use SHOW COLUMNS via PDO"),
            ("mysql_list_processes", "Use SHOW PROCESSLIST via PDO"),
            ("mysql_list_tables", "Use SHOW TABLES via PDO"),
            ("mysql_num_fields", "Use PDOStatement::columnCount()"),
            ("mysql_num_rows", "Use PDOStatement::rowCount()"),
            ("mysql_pconnect", "Use PDO with persistent connections"),
            ("mysql_query", "Use PDO::query()"),
            ("mysql_real_escape_string", "Use prepared statements"),
            ("mysql_result", "Use PDOStatement::fetchColumn()"),
            ("mysql_select_db", "Specify database in PDO DSN"),
            ("mysql_set_charset", "Use PDO DSN charset parameter"),
            ("mysql_stat", "Use PDO"),
            ("mysql_tablename", "Use PDO"),
            ("mysql_thread_id", "Use PDO"),
            ("ereg", "Use preg_match()"),
            ("ereg_replace", "Use preg_replace()"),
            ("split", "Use explode() or preg_split()"),
            ("set_magic_quotes_runtime", "Removed — magic quotes are gone"),
            ("set_socket_blocking", "Use stream_set_blocking()"),
            ("mcrypt_encrypt", "Use sodium or openssl_encrypt()"),
            ("mcrypt_decrypt", "Use sodium or openssl_decrypt()"),
        ],
        "deprecated": [
            ("create_function", "Use anonymous functions (closures)"),
            ("each", "Use foreach"),
            ("$HTTP_RAW_POST_DATA", "Use php://input"),
        ],
    },
    "7.1": {
        "removed": [
            ("mcrypt_create_iv", "Use random_bytes()"),
        ],
        "deprecated": [],
    },
    "7.2": {
        "removed": [],
        "deprecated": [
            ("create_function", "Use anonymous functions"),
            ("each", "Use foreach"),
        ],
    },
    "7.3": {
        "removed": [],
        "deprecated": [
            ("image2wbmp", "Use imagewbmp()"),
            ("FILTER_FLAG_SCHEME_REQUIRED", "Removed flag"),
            ("FILTER_FLAG_HOST_REQUIRED", "Removed flag"),
        ],
    },
    "7.4": {
        "removed": [],
        "deprecated": [
            ("real", "Use float"),
            ("magic_quotes_runtime", "Already removed"),
            ("array_key_exists() on objects", "Use isset() or property_exists()"),
        ],
    },
    "8.0": {
        "removed": [
            ("create_function", "Use anonymous functions"),
            ("each", "Use foreach"),
            ("mysqli_report", "Removed constants MYSQLI_REPORT_*"),
            ("money_format", "Use NumberFormatter::formatCurrency()"),
            ("ezmlm_hash", "Removed"),
            ("get_magic_quotes_gpc", "Always returns false, removed"),
            ("get_magic_quotes_runtime", "Always returns false, removed"),
            ("hebrevc", "Use hebrev()"),
            ("convert_cyr_string", "Use mb_convert_encoding() or iconv()"),
            ("restore_include_path", "Removed"),
            ("allow_url_include INI", "Removed"),
            ("@ operator on fatal errors", "No longer silences"),
        ],
        "deprecated": [
            ("strftime", "Use date() or DateTime::format()"),
            ("gmstrftime", "Use gmdate()"),
            ("mktime() without args", "An E_DEPRECATED is raised"),
            ("strptime", "Use date_parse_from_format()"),
        ],
    },
    "8.1": {
        "removed": [
            ("FILTER_FLAG_SCHEME_REQUIRED", "Use FILTER_FLAG_HOSTNAME or proper validation"),
            ("FILTER_FLAG_HOST_REQUIRED", "Use FILTER_FLAG_HOSTNAME"),
            ("oci_execute with OCI_DEFAULT", "Use oci_execute()"),
            ("odbc_result_all", "Use odbc_fetch_array()"),
            ("key(), current(), next(), prev(), reset() on objects", "Use ArrayIterator"),
        ],
        "deprecated": [
            ("strftime", "Use date() or IntlDateFormatter"),
            ("gmstrftime", "Use gmdate()"),
            ("date_sunrise", "Use date_sun_info()"),
            ("date_sunset", "Use date_sun_info()"),
            ("strptime", "Use date_parse_from_format()"),
            ("utf8_encode", "Use mb_convert_encoding()"),
            ("utf8_decode", "Use mb_convert_encoding()"),
        ],
    },
    "8.2": {
        "removed": [],
        "deprecated": [
            ("utf8_encode", "Use mb_convert_encoding() or UConverter"),
            ("utf8_decode", "Use mb_convert_encoding() or UConverter"),
            (
                "Dynamic properties",
                "Declare properties explicitly or use #[AllowDynamicProperties]",
            ),
            ("${} string interpolation", "Use {$var} instead"),
            ("Mbstring: Base64, Uuencode, QPrint", "Use base64_encode/decode"),
            (
                "Partially supported callables",
                "Use $callable() closure or first-class callable syntax",
            ),
        ],
    },
    "8.3": {
        "removed": [],
        "deprecated": [
            ("assert_options", "Use ini_set() for assert.* INI settings"),
            ("get_class() without args", "Use __CLASS__ or get_class($this)"),
            ("get_parent_class() without args", "Use parent::class"),
        ],
    },
}

VERSION_ORDER = ["7.0", "7.1", "7.2", "7.3", "7.4", "8.0", "8.1", "8.2", "8.3"]


def discover_php_files(root: Path) -> list[Path]:
    """discover php files.

    Args:
        root: Description.

    Returns:
        Description.
    """
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


def audit_file(filepath: Path, target_version: str) -> dict:
    """audit file.

    Args:
        filepath: Description.
        target_version: Description.

    Returns:
        Description.
    """
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return {"file": str(filepath), "findings": []}

    findings = []

    # Collect all removed/deprecated for versions up to target
    for version in VERSION_ORDER:
        if version > target_version:
            break
        info = DEPRECATED.get(version, {"removed": [], "deprecated": []})

        # Check removed
        for func_name, replacement in info["removed"]:
            # Match function calls: func_name(
            pattern = re.compile(r"\b" + re.escape(func_name) + r"\s*\(")
            for match in pattern.finditer(source):
                line = source[: match.start()].count("\n") + 1
                findings.append(
                    {
                        "line": line,
                        "severity": "ERROR",
                        "function": func_name,
                        "version": version,
                        "type": "removed",
                        "message": f"Removed in PHP {version}: {func_name}()",
                        "fix": replacement,
                    }
                )

        # Check deprecated
        for func_name, replacement in info["deprecated"]:
            pattern = re.compile(r"\b" + re.escape(func_name) + r"\s*\(")
            for match in pattern.finditer(source):
                line = source[: match.start()].count("\n") + 1
                findings.append(
                    {
                        "line": line,
                        "severity": "WARNING",
                        "function": func_name,
                        "version": version,
                        "type": "deprecated",
                        "message": f"Deprecated in PHP {version}: {func_name}()",
                        "fix": replacement,
                    }
                )

    return {"file": str(filepath), "findings": findings}


def print_report(results: list[dict], target_version: str) -> None:
    """Print report.

    Args:
        results: Description.
        target_version: Description.

    Returns:
        Description.
    """
    all_findings = []
    for r in results:
        all_findings.extend(r["findings"])

    errors = sum(1 for f in all_findings if f["severity"] == "ERROR")
    warnings = sum(1 for f in all_findings if f["severity"] == "WARNING")

    # Group by file
    for r in results:
        if not r["findings"]:
            continue
        status = "❌" if any(f["severity"] == "ERROR" for f in r["findings"]) else "⚠"
        print(f"\n{'=' * 70}")
        print(f" {status} {r['file']} ({len(r['findings'])} issues)")
        print(f"{'=' * 70}")
        for f in r["findings"]:
            tag = "ERROR" if f["severity"] == "ERROR" else "WARN"
            print(f"     {f['line']:4d} | [{tag}] {f['message']}")
            if f["fix"]:
                print(f"          |        Fix: {f['fix']}")

    print(f"\n{'=' * 70}")
    print(f" VERSION AUDIT (target: PHP {target_version})")
    print(f"{'=' * 70}")
    print(f"   Files: {len(results)}  |  ERRORS: {errors}  |  WARNINGS: {warnings}")

    if errors == 0 and warnings == 0:
        print(f"   ✅ Fully compatible with PHP {target_version}")
    elif errors > 0:
        print(f"   ❌ {errors} functions removed in PHP {target_version} — must fix before upgrade")
    else:
        print(f"   ⚠ {warnings} deprecated — safe now, should fix for future PHP versions")

    print()


def print_json(results: list[dict], target_version: str) -> None:
    """Print json.

    Args:
        results: Description.
        target_version: Description.

    Returns:
        Description.
    """
    all_findings = []
    for r in results:
        all_findings.extend(r["findings"])

    output = {
        "target_php": target_version,
        "summary": {
            "files": len(results),
            "errors": sum(1 for f in all_findings if f["severity"] == "ERROR"),
            "warnings": sum(1 for f in all_findings if f["severity"] == "WARNING"),
        },
        "findings_by_file": results,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


def main():
    """main."""
    parser = argparse.ArgumentParser(description="php_version_audit.py - PHP version compatibility")
    parser.add_argument("path", help="PHP file or directory")
    parser.add_argument("--recursive", "-r", action="store_true")
    parser.add_argument("--target", default="8.1", help="Target PHP version (default: 8.1)")
    parser.add_argument("--json", "-j", action="store_true")
    parser.add_argument("--version", action="version", version="php_version_audit.py v1.0.0")

    args = parser.parse_args()
    target_path = Path(args.path)
    if not target_path.exists():
        print(f"Not found", file=sys.stderr)
        sys.exit(1)

    print(f"\n📅 PHP Version Audit v1.0.0 — target: PHP {args.target}")
    print(f"{'=' * 70}")

    files = (
        [target_path]
        if target_path.is_file()
        else (
            discover_php_files(target_path) if args.recursive else sorted(target_path.glob("*.php"))
        )
    )
    if not files:
        print("No PHP files")
        sys.exit(0)

    print(f"   {len(files)} PHP file(s)")
    results = [audit_file(f, args.target) for f in files]

    if args.json:
        print_json(results, args.target)
    else:
        print_report(results, args.target)


if __name__ == "__main__":
    main()
