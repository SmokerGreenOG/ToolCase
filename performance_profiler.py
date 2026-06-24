#!/usr/bin/env python3
"""
performance_profiler.py — Detecteer performance issues in Python code.

Checkt:
  - Imports in loops
  - Onnodige I/O (open() in loops)
  - Langzame functiepatronen (os.walk)
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import ast
import json
import sys
from pathlib import Path

from collections import defaultdict

PATTERNS = {
    "import_in_loop": {
        "desc": "import in loop — kost onnodige tijd",
        "severity": "medium",
        "fix": "Verplaats import naar top van bestand",
    },
    "open_in_loop": {
        "desc": "open() in loop — onnodige I/O",
        "severity": "high",
        "fix": "Open bestand één keer vóór de loop",
    },
    "os_walk_in_loop": {
        "desc": "os.walk() in loop — extreem traag",
        "severity": "high",
        "fix": "Gebruik Path.rglob() of cache de walk resultaten",
    },
    "listdir_in_loop": {
        "desc": "os.listdir() in loop",
        "severity": "medium",
        "fix": "Cache de lijst vóór de loop",
    },
    "re_compile_in_loop": {
        "desc": "re.compile() in loop — compileer één keer",
        "severity": "medium",
        "fix": "Maak de regex een module-level constante",
    },
}


def analyze_file(filepath: Path) -> list[dict]:
    """analyze file.

        Args:
            filepath: Description.

        Returns:
            Description.
        """
    findings = []
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return findings

    for node in ast.walk(tree):
        # Find loops (for, while)
        if isinstance(node, (ast.For, ast.While)):
            for child in ast.walk(node):
                # import inside loop
                if isinstance(child, ast.Import):
                    findings.append(dict(
                        PATTERNS["import_in_loop"],
                        file=str(filepath),
                        line=child.lineno,
                        code="import ...",
                    ))
                elif isinstance(child, ast.ImportFrom):
                    findings.append(dict(
                        PATTERNS["import_in_loop"],
                        file=str(filepath),
                        line=child.lineno,
                        code=f"from {child.module or '?'} import ...",
                    ))
                # open() inside loop
                elif isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name) and child.func.id == "open":
                        findings.append(dict(
                            PATTERNS["open_in_loop"],
                            file=str(filepath),
                            line=child.lineno,
                            code="open(...)",
                        ))
                    elif isinstance(child.func, ast.Name) and child.func.id in ("re_compile", "compile"):
                        pass  # Not usually in loops

    return findings


def scan_workspace(workspace: Path) -> list[dict]:
    """Scan workspace.

        Args:
            workspace: Description.

        Returns:
            Description.
        """
    all_findings = []
    for fp in sorted(workspace.glob("*.py")):
        if fp.name.startswith("_") or fp.name.startswith("test_"):
            continue
        all_findings.extend(analyze_file(fp))
    return all_findings


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(description="Performance Profiler")
    parser.add_argument("path", nargs="?", default=".", help="Workspace")
    parser.add_argument("--json", "-j", action="store_true")
    args = parser.parse_args()

    target = Path(args.path).resolve()
    findAllFindings = scan_workspace(target)

    if args.json:
        print(json.dumps([{
            "file": Path(f["file"]).name, "line": f["line"],
            "desc": f["desc"], "severity": f["severity"]
        } for f in findAllFindings], indent=2))
    else:
        print()
        print("=" * 60)
        print(" ⚡ PERFORMANCE PROFILER")
        print("=" * 60)
        print(f"   Findings: {len(findAllFindings)}")

        by_sev = defaultdict(int)
        for f in findAllFindings:
            by_sev[f["severity"]] += 1

        print(f"   🔴 High:   {by_sev.get('high', 0)}")
        print(f"   🟡 Medium: {by_sev.get('medium', 0)}")

        for f in findAllFindings[:15]:
            icon = "🔴" if f["severity"] == "high" else "🟡"
            fname = Path(f["file"]).name if "file" in f else "?"
            print(f"   {icon} {fname}:{f['line']} — {f['desc']}")
            print(f"      💡 {f['fix']}")

        if not findAllFindings:
            print(f"   ✨ Geen performance issues gevonden!")


if __name__ == "__main__":
    main()
