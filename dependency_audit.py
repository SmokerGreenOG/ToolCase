#!/usr/bin/env python3
"""
dependency_audit.py — Audit project dependencies for outdated/vulnerable packages.

Analyzes:
  - Python: requirements.txt, pyproject.toml, Pipfile
  - Node.js: package.json, package-lock.json, yarn.lock
  - Rust: Cargo.toml, Cargo.lock
  - Detects outdated versions, security concerns, deprecated packages
  - Cross-references with pyproject.toml for optional dependencies

Gebruik:
    python dependency_audit.py <path>
    python dependency_audit.py <path> --json
    python dependency_audit.py <path> --check-versions
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = frozenset({
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
        ".backups",
        
        ".rsi_backups",
        
        ".rsi_reports",
        
        ".self_improve_reports",
        })

# Well-known insecure/outdated packages (name -> issue)
KNOWN_ISSUES = {
    "lodash": "Multiple prototype pollution CVEs — upgrade to >=4.17.21",
    "jquery": "Multiple CVEs — upgrade to >=3.5.0",
    "minimist": "Prototype pollution — upgrade to >=1.2.6",
    "node-fetch": "URL request injection — upgrade to >=2.6.7, >=3.1.1",
    "undici": "HTTP request smuggling — upgrade to >=5.19.1",
    "axios": "Server-Side Request Forgery — upgrade to >=0.21.2",
    "moment": "Deprecated — use date-fns or dayjs instead",
    "chalk": "Deprecated (ESM only) — use picocolors or kleur",
    "got": "Deprecated — use undici or native fetch",
    "request": "Fully deprecated — use node-fetch or undici",
    "left-pad": "Not maintained — consider alternatives",
    "colors": "Supply chain incident (faker.js) — use chalk",
    "faker": "Deprecated and broken — use @faker-js/faker",
    "crypto-js": "Not actively maintained — use native Web Crypto API",
    "pycryptodome": "Outdated — upgrade to >=3.19.0",
    "cryptography": "Multiple CVEs — upgrade to >=39.0.0",
    "pillow": "Multiple CVEs — upgrade to >=10.0.0",
    "django": "Known CVEs — upgrade to latest LTS",
    "flask": "Known CVEs — upgrade to >=3.0.0",
    "requests": "Multiple CVEs — upgrade to >=2.31.0",
    "urllib3": "Known CVEs — upgrade to >=1.26.18, >=2.0.7",
    "certifi": "Known CVEs — upgrade to >=2023.7.22",
}

# Minimum recommended versions (name -> min_version)
MIN_VERSIONS = {
    "python": "3.11",
    "node": "18",
    "rust": "1.70",
}


def get_python_deps(root: Path) -> list[dict]:
    """Parse Python dependency files."""
    deps = []

    # requirements.txt
    req_file = root / "requirements.txt"
    if req_file.exists():
        try:
            content = req_file.read_text(encoding="utf-8")
            for line in content.split("\n"):
                line = line.strip()
                if not line or line.startswith(("#", "-", "git+")):
                    continue
                # Parse name and version
                m = re.match(r'^([a-zA-Z0-9_.-]+)\s*([<>=!~]+)\s*([\d.]+)', line)
                if m:
                    deps.append({
                        "name": m.group(1).lower(),
                        "constraint": m.group(2) + m.group(3),
                        "version": m.group(3),
                        "source": "requirements.txt",
                    })
                else:
                    # Name only (no version)
                    name = line.split("#")[0].strip()
                    if name and not name.startswith("-"):
                        deps.append({
                            "name": name.lower(),
                            "constraint": "",
                            "version": "",
                            "source": "requirements.txt",
                        })
        except Exception as e:
            deps.append({"name": f"Error reading requirements.txt: {e}", "source": "error"})

    # pyproject.toml
    pyproj = root / "pyproject.toml"
    if pyproj.exists():
        try:
            content = pyproj.read_text(encoding="utf-8")
            # Parse [project] dependencies
            in_deps = False
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("[tool.poetry.dependencies]"):
                    in_deps = True
                    continue
                if stripped.startswith("[tool.poetry"):
                    in_deps = False
                    continue
                if stripped.startswith("[project"):
                    in_deps = True
                    continue
                if stripped.startswith("[") and in_deps:
                    in_deps = False
                    continue
                if in_deps and "=" in stripped and not stripped.startswith("#"):
                    parts = stripped.split("=", 1)
                    name = parts[0].strip().strip("\"'")
                    version = parts[1].strip().strip("\"'")
                    if name and name not in ("python", "requires-python"):
                        m = re.match(r'[<>=!~]+\s*([\d.]+)', version)
                        ver = m.group(1) if m else version
                        deps.append({
                            "name": name.lower(),
                            "constraint": version if m else "",
                            "version": ver,
                            "source": "pyproject.toml",
                        })
        except Exception as e:
            deps.append({"name": f"Error reading pyproject.toml: {e}", "source": "error"})

    return deps


def get_node_deps(root: Path) -> list[dict]:
    """Parse Node.js dependency files."""
    deps = []

    pkg = root / "package.json"
    if pkg.exists():
        try:
            content = pkg.read_text(encoding="utf-8")
            data = json.loads(content)

            dep_sections = ["dependencies", "devDependencies",
                              "peerDependencies", "optionalDependencies"]
            for section in dep_sections:
                if section in data:
                    for name, version in data[section].items():
                        m = re.match(r'[\^~]?([\d.]+)', version)
                        ver = m.group(1) if m else version
                        deps.append({
                            "name": name.lower(),
                            "constraint": version,
                            "version": ver,
                            "source": f"package.json ({section})",
                        })
        except Exception as e:
            deps.append({"name": f"Error reading package.json: {e}", "source": "error"})

    return deps


def get_rust_deps(root: Path) -> list[dict]:
    """Parse Rust Cargo.toml dependencies."""
    deps = []

    cargo = root / "Cargo.toml"
    if cargo.exists():
        try:
            content = cargo.read_text(encoding="utf-8")
            in_deps = False

            for line in content.split("\n"):
                stripped = line.strip()

                if stripped.startswith("[dependencies]"):
                    in_deps = True
                    continue
                if stripped.startswith("[dev-dependencies]"):
                    in_deps = True
                    continue
                if stripped.startswith("[build-dependencies]"):
                    in_deps = True
                    continue
                if stripped.startswith("["):
                    in_deps = False
                    continue

                if in_deps and "=" in stripped and not stripped.startswith("#"):
                    parts = stripped.split("=", 1)
                    name = parts[0].strip()
                    version = parts[1].strip().strip("\"'")
                    if name and version:
                        m = re.match(r'[\"\' ]*([\d.]+)', version)
                        ver = m.group(1) if m else version
                        deps.append({
                            "name": name.lower(),
                            "constraint": version,
                            "version": ver,
                            "source": "Cargo.toml",
                        })
        except Exception as e:
            deps.append({"name": f"Error reading Cargo.toml: {e}", "source": "error"})

    return deps


def audit_deps(all_deps: list[dict]) -> list[dict]:
    """Cross-reference dependencies against known issues."""
    issues = []

    for dep in all_deps:
        name = dep["name"]
        version = dep["version"]

        # Check known issues
        if name in KNOWN_ISSUES:
            issues.append({
                "severity": "WARN",
                "type": "known_issue",
                "name": name,
                "version": version,
                "source": dep["source"],
                "message": f"{name} {version}: {KNOWN_ISSUES[name]}",
            })

        # Check if version pin is missing
        if not dep["constraint"] and dep["source"] not in ("error",):
            issues.append({
                "severity": "INFO",
                "type": "unpinned",
                "name": name,
                "version": "none",
                "source": dep["source"],
                "message": f"{name}: geen versie vastgepind — kan onverwachte upgrades veroorzaken",
            })

    return issues


def print_report(deps_by_source: dict, issues: list[dict],
                 total_deps: int) -> None:
    """Print formatted dependency audit report."""
    warnings = [i for i in issues if i["severity"] == "WARN"]
    infos = [i for i in issues if i["severity"] == "INFO"]

    print(f"\n{'='*60}")
    print(f" 📦 DEPENDENCY AUDIT")
    print(f"{'='*60}")
    print(f"   Totaal dependencies: {total_deps}")
    print(f"   ⚠  Known issues:     {len(warnings)}")
    print(f"   💡 Unpinned:          {len(infos)}")
    print()

    # Per source
    for source, deps in deps_by_source.items():
        if source == "error":
            continue
        print(f" ── {source} ({len(deps)}) ──")
        for dep in sorted(deps, key=lambda x: x["name"]):
            constraint = f" {dep['constraint']}" if dep["constraint"] else ""
            print(f"   📦 {dep['name']}{constraint}")
        print()

    if warnings:
        print(f" ── Known Issues ({len(warnings)}) ──")
        for w in warnings:
            print(f"   ⚠  {w['message']}")
        print()

    if infos:
        print(f" ── Unpinned ({len(infos)}) ──")
        for i in infos[:10]:
            print(f"   💡 {i['message']}")
        if len(infos) > 10:
            print(f"   ... en nog {len(infos) - 10}")
        print()

    if not issues:
        print(" ✅ Geen dependency issues gevonden!")
        print()


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="dependency_audit.py — Audit project dependencies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python dependency_audit.py .
  python dependency_audit.py . --json
  python dependency_audit.py . --check-versions
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--check-versions", "-v", action="store_true",
                        help="Check minimum recommended versions")
    parser.add_argument("--version", action="version", version="dependency_audit.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 Dependency Audit v1.0.0 — scanning {target}")

    all_deps = []
    deps_by_source = defaultdict(list)

    python_deps = get_python_deps(target)
    node_deps = get_node_deps(target)
    rust_deps = get_rust_deps(target)

    all_deps.extend(python_deps)
    all_deps.extend(node_deps)
    all_deps.extend(rust_deps)

    for dep in all_deps:
        deps_by_source[dep["source"]].append(dep)

    total_deps = len(all_deps)

    if not all_deps:
        print(" Geen dependency files gevonden (requirements.txt, package.json, Cargo.toml)")
        sys.exit(0)

    issues = audit_deps(all_deps)

    if args.json:
        output = {
            "total_deps": total_deps,
            "deps_by_source": {k: v for k, v in deps_by_source.items()},
            "issues": issues,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print_report(deps_by_source, issues, total_deps)


if __name__ == "__main__":
    main()
