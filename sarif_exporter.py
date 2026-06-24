#!/usr/bin/env python3
"""
sarif_exporter.py — Export ToolCase findings as SARIF v2.1.0.

SARIF (Static Analysis Results Interchange Format) enables GitHub Code Scanning
to display ToolCase security findings directly in the Security tab.

Usage:
    # Pipe from scanner
    python security_scan.py . --json | python sarif_exporter.py --output toolcase.sarif

    # Direct scan + export
    python sarif_exporter.py --scan security --path . --output toolcase.sarif

    # Multiple scanners merged
    python sarif_exporter.py --scan security,php_checker --path src/ -o combined.sarif

    # Validate output
    python sarif_exporter.py --validate toolcase.sarif

GitHub Actions integration:
    - name: ToolCase Security Scan
      run: python sarif_exporter.py --scan security --path . -o toolcase.sarif
    - name: Upload SARIF
      uses: github/codeql-action/upload-sarif@v3
      with:
        sarif_file: toolcase.sarif
"""
__maker__ = "SmokerGreenOG"

import _protect

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOOLCASE_DRIVER = {
    "name": "ToolCase",
    "fullName": "ToolCase — AI Agent Code Toolkit",
    "organization": "SmokerGreenOG",
    "informationUri": "https://github.com/SmokerGreenOG/ToolCase",
    "semanticVersion": "5.4.0",
    "rules": [],  # Populated during export
}

# Mapping: ToolCase risk → SARIF level
RISK_TO_SARIF_LEVEL = {
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "note",
    "INFO": "note",
}

# Mapping: ToolCase risk → SARIF rank (0.0-10.0, higher = more severe)
RISK_TO_RANK = {
    "HIGH": 9.0,
    "MEDIUM": 6.0,
    "LOW": 3.0,
    "INFO": 1.5,
}

# SARIF version
SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/"
    "master/Schemata/sarif-schema-2.1.0.json"
)


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------


def _make_rule_id(pattern: str) -> str:
    """Convert pattern name to SARIF-compatible rule ID."""
    return f"toolcase/{pattern}".replace(" ", "_").lower()


def _get_rule_metadata(pattern: str, fix: str = "") -> dict[str, Any]:
    """Get SARIF rule metadata for a ToolCase pattern."""
    descriptions = {
        "api_key": "Hardcoded API key found in source code",
        "password": "Hardcoded password or secret",
        "token": "Hardcoded access token (JWT, bearer, etc.)",
        "aws_key": "AWS access key in source code",
        "private_key": "Private key material in source code",
        "connection_string": "Database connection string with credentials",
        "eval_exec": "Use of eval() or exec() — arbitrary code execution risk",  # toolcase: ignore-security
        "pickle_usage": "Unsafe pickle deserialization",
        "shell_injection": "Shell injection via shell=True or os.system",  # toolcase: ignore-security
        "sql_injection": "Potential SQL injection via string interpolation",
        "yaml_load": "Unsafe YAML loading (use yaml.safe_load)",
        "assert_used": "Assert in production code (stripped with -O)",
        "hardcoded_ip": "Hardcoded IP address — deployment inflexibility",
        "localhost_url": "Hardcoded localhost URL — breaks in production",
        "commented_auth": "Commented-out credentials — leak intent",
        "env_with_secret": "Secret in environment variable — ensure .gitignore",
        "read_error": "File could not be read (permissions/encoding)",
        "backtick_exec": "PHP backtick operator — potential shell execution",
        "command_injection": "PHP command injection via user input",
        "hardcoded_password": "Hardcoded password in PHP code",
        "file_get_contents_user_input": "User input in file_get_contents",
        "no_csrf_token": "Form without CSRF token",
        "short_open_tags": "PHP short open tags — deprecated",
        "display_errors_enabled": "PHP display_errors enabled — information leak",
        "deprecated_mysql": "Deprecated mysql_* functions",
    }
    return {
        "id": _make_rule_id(pattern),
        "shortDescription": {
            "text": descriptions.get(pattern, f"ToolCase pattern: {pattern}"),
        },
        "fullDescription": {
            "text": fix or descriptions.get(pattern, f"Security finding: {pattern}"),
        },
        "helpUri": f"https://github.com/SmokerGreenOG/ToolCase#security--compliance",
        "properties": {
            "tags": ["security", "toolcase"],
        },
    }


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------


def _fingerprint(finding: dict[str, Any]) -> str:
    """Generate a stable GUID for SARIF partialFingerprints from finding data."""
    raw = (
        f"{finding.get('file', '')}:"
        f"{finding.get('line', 0)}:"
        f"{finding.get('pattern', '')}:"
        f"{finding.get('risk', '')}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Finding → SARIF result
# ---------------------------------------------------------------------------


def _finding_to_result(finding: dict[str, Any],
                       repo_root: Path) -> dict[str, Any]:
    """Convert a single ToolCase finding to a SARIF result."""
    file_path = finding.get("file", "")
    rel_path = file_path
    try:
        fp = Path(file_path)
        if fp.is_absolute():
            try:
                rel_path = str(fp.relative_to(repo_root)).replace("\\", "/")
            except ValueError:
                rel_path = fp.name
    except Exception:
        pass

    line = finding.get("line", 1)
    risk = finding.get("risk", "LOW").upper()
    pattern = finding.get("pattern", "unknown")
    match_text = finding.get("match", "")[:200]
    context = finding.get("context", "")[:200]
    fix_text = finding.get("fix", "")

    rule_id = _make_rule_id(pattern)
    level = RISK_TO_SARIF_LEVEL.get(risk, "note")
    rank = RISK_TO_RANK.get(risk, 3.0)

    message_text = f"[{risk}] {pattern}: {fix_text or match_text}"
    if context:
        message_text += f"\n  Context: {context}"

    return {
        "ruleId": rule_id,
        "ruleIndex": 0,  # Will be resolved per run
        "level": level,
        "message": {
            "text": message_text,
        },
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": rel_path,
                    },
                    "region": {
                        "startLine": line,
                        "snippet": {
                            "text": context[:150] if context else match_text[:150],
                        },
                    },
                },
            },
        ],
        "partialFingerprints": {
            "primary": _fingerprint(finding),
        },
        "properties": {
            "toolcase:risk": risk,
            "toolcase:pattern": pattern,
            "toolcase:rank": rank,
        },
    }


# ---------------------------------------------------------------------------
# Core: Build SARIF
# ---------------------------------------------------------------------------


def build_sarif(findings: list[dict[str, Any]],
                repo_root: Path | None = None,
                tool_name: str = "ToolCase",
                scan_stats: dict[str, int] | None = None) -> dict[str, Any]:
    """Build a complete SARIF v2.1.0 document from ToolCase findings."""

    if repo_root is None:
        repo_root = Path.cwd()

    # Collect unique rules
    rules: dict[str, dict] = {}
    for f in findings:
        pattern = f.get("pattern", "unknown")
        rid = _make_rule_id(pattern)
        if rid not in rules:
            rules[rid] = _get_rule_metadata(pattern, f.get("fix", ""))

    # Build results
    results = [_finding_to_result(f, repo_root) for f in findings]

    # Count by level
    by_level = {"error": 0, "warning": 0, "note": 0}
    for r in results:
        lvl = r["level"]
        if lvl in by_level:
            by_level[lvl] += 1

    # Build the run
    driver = dict(TOOLCASE_DRIVER)
    driver["rules"] = list(rules.values())

    run: dict[str, Any] = {
        "tool": {
            "driver": driver,
        },
        "results": results,
        "properties": {
            "toolcase:scan_stats": scan_stats or {},
        },
    }

    # Build the SARIF document
    sarif = {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [run],
    }

    return sarif


# ---------------------------------------------------------------------------
# Scanner runners
# ---------------------------------------------------------------------------


def run_scanner(scanner_name: str, path: str) -> dict[str, Any]:
    """Run a ToolCase scanner and return its findings + stats."""
    target = Path(path).resolve()
    scanner_script = f"{scanner_name}.py" if not scanner_name.endswith(".py") else scanner_name

    try:
        proc = subprocess.run(
            [sys.executable, scanner_script, str(target), "--json"],
            capture_output=True, text=True, timeout=120,
            cwd=str(Path(__file__).parent),
        )
    except subprocess.TimeoutExpired:
        return {"findings": [], "scan_stats": {"error": "Scanner timed out"}}
    except FileNotFoundError:
        return {"findings": [], "scan_stats": {"error": f"Scanner '{scanner_name}' not found"}}

    # Parse JSON from output
    output = proc.stdout
    idx = output.find('{\n  "')
    if idx < 0:
        idx = output.find('{"')
    if idx >= 0:
        try:
            data = json.loads(output[idx:])
            return {
                "findings": data.get("findings", []),
                "scan_stats": data.get("scan_stats", {}),
            }
        except json.JSONDecodeError:
            pass

    return {"findings": [], "scan_stats": {"error": "Could not parse scanner output"}}


def run_multiple_scanners(scanner_names: list[str], path: str) -> dict[str, Any]:
    """Run multiple scanners and merge findings."""
    all_findings: list[dict] = []
    all_stats: dict[str, Any] = {}

    for name in scanner_names:
        result = run_scanner(name.strip(), path)
        all_findings.extend(result["findings"])
        all_stats[name.strip()] = result.get("scan_stats", {})

    return {"findings": all_findings, "scan_stats": all_stats}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_sarif(sarif_path: str) -> tuple[bool, str]:
    """Basic SARIF structure validation (no full schema check)."""
    try:
        with open(sarif_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return False, str(e)

    errors = []

    # Check required top-level fields
    if data.get("version") != SARIF_VERSION:
        errors.append(f"Expected version {SARIF_VERSION}, got {data.get('version')}")

    if "$schema" not in data:
        errors.append("Missing $schema")

    runs = data.get("runs", [])
    if not runs:
        errors.append("No runs in SARIF document")
    else:
        run = runs[0]
        if "tool" not in run:
            errors.append("Missing tool in run")
        if "results" not in run:
            errors.append("Missing results in run")
        else:
            for i, r in enumerate(run["results"]):
                if "ruleId" not in r:
                    errors.append(f"Result {i}: missing ruleId")
                if "message" not in r:
                    errors.append(f"Result {i}: missing message")
                if "locations" not in r:
                    errors.append(f"Result {i}: missing locations")

    if errors:
        return False, "; ".join(errors)
    return True, "Valid SARIF v2.1.0"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="sarif_exporter.py — Export ToolCase findings as SARIF v2.1.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python security_scan.py . --json | python sarif_exporter.py -o results.sarif
  python sarif_exporter.py --scan security --path . -o results.sarif
  python sarif_exporter.py --scan security,php_checker --path src/ -o combined.sarif
  python sarif_exporter.py --validate results.sarif
        """,
    )
    parser.add_argument("--scan", "-s",
                        help="Comma-separated scanner names (security, php_checker, etc.)")
    parser.add_argument("--path", "-p", default=".",
                        help="Path to scan (default: current dir)")
    parser.add_argument("--output", "-o",
                        help="Output SARIF file (default: stdout)")
    parser.add_argument("--stdin", action="store_true",
                        help="Read JSON findings from stdin")
    parser.add_argument("--repo-root",
                        help="Repository root for relative paths (default: current dir)")
    parser.add_argument("--validate", metavar="FILE",
                        help="Validate an existing SARIF file")
    parser.add_argument("--version", action="version",
                        version="sarif_exporter.py v1.0.0")

    args = parser.parse_args()

    # Validation mode
    if args.validate:
        ok, msg = validate_sarif(args.validate)
        if ok:
            print(f"✅ {msg}")
            sys.exit(0)
        else:
            print(f"❌ {msg}", file=sys.stderr)
            sys.exit(1)

    # Collect findings
    findings: list[dict] = []
    scan_stats: dict[str, int] = {}

    if args.stdin:
        # Read from stdin — handle banners before JSON
        raw = sys.stdin.read()
        idx = raw.find('{\n  "')
        if idx < 0:
            idx = raw.find('{"')
        if idx >= 0:
            try:
                data = json.loads(raw[idx:])
                findings = data.get("findings", [])
                scan_stats = data.get("scan_stats", {})
            except json.JSONDecodeError:
                print("❌ Invalid JSON on stdin", file=sys.stderr)
                sys.exit(1)
        else:
            print("❌ No JSON found on stdin", file=sys.stderr)
            sys.exit(1)
    elif args.scan:
        scanners = [s.strip() for s in args.scan.split(",")]
        result = run_multiple_scanners(scanners, args.path)
        findings = result["findings"]
        scan_stats = result.get("scan_stats", {})
    else:
        # Read from stdin by default — handle banners before JSON
        raw = sys.stdin.read()
        if raw.strip():
            idx = raw.find('{\n  "')
            if idx < 0:
                idx = raw.find('{"')
            if idx >= 0:
                try:
                    data = json.loads(raw[idx:])
                    findings = data.get("findings", [])
                    scan_stats = data.get("scan_stats", {})
                except json.JSONDecodeError:
                    print("❌ Invalid JSON on stdin", file=sys.stderr)
                    sys.exit(1)
            else:
                # No JSON bracket — maybe it's a direct findings array?
                print("❌ No JSON found on stdin", file=sys.stderr)
                sys.exit(1)
        else:
            print("❌ No input. Pipe scanner output or use --scan.", file=sys.stderr)
            sys.exit(1)

    if not findings:
        # Still produce a valid SARIF with zero results
        pass

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(args.path).resolve()
    sarif = build_sarif(findings, repo_root, scan_stats=scan_stats)

    sarif_json = json.dumps(sarif, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(sarif_json, encoding="utf-8")
        print(f"✅ SARIF written to {args.output} "
              f"({len(findings)} findings, "
              f"{sarif['runs'][0]['tool']['driver']['name']})")
    else:
        print(sarif_json)


if __name__ == "__main__":
    main()
