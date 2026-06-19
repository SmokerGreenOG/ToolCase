#!/usr/bin/env python3
"""
code_churn_analyzer.py — Analyseer welke files het vaakst wijzigen (hotspots).

Hotspot = wijzigingen × file_grootte. Hoe vaker gewijzigd + hoe groter = hoe riskanter.
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import subprocess
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.resolve()


def analyze() -> dict:
    results = {}
    stats = defaultdict(lambda: {"changes": 0, "lines": 0, "score": 0})

    # Get file sizes
    for fp in sorted(ROOT.glob("*.py")):
        if fp.name.startswith("_") or fp.name.startswith("test_"):
            continue
        lines = len(fp.read_text(encoding="utf-8", errors="replace").splitlines())
        stats[fp.name]["lines"] = lines

    # Get change frequency from git log
    try:
        r = subprocess.run(
            ["git", "log", "--pretty=format:", "--name-only"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=15
        )
        for line in r.stdout.strip().split("\n"):
            line = line.strip()
            if line and line.endswith(".py") and not line.startswith(("_", "test_")):
                stats[line]["changes"] += 1
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Compute hotspot score
    for fname, s in stats.items():
        if s["lines"] > 0:
            s["score"] = round(s["changes"] * s["lines"] / 1000, 1)

    # Sort by score
    sorted_stats = sorted(stats.items(), key=lambda x: -x[1]["score"])

    total_changes = sum(s["changes"] for _, s in sorted_stats)
    total_files = len(sorted_stats)
    hotspots = [(n, s) for n, s in sorted_stats if s["score"] > 2]

    return {
        "total_files": total_files,
        "total_changes": total_changes,
        "hotspots": len(hotspots),
        "files": [(n, s["changes"], s["lines"], s["score"]) for n, s in sorted_stats],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Code Churn Analyzer — Hotspot detectie")
    parser.add_argument("--json", "-j", action="store_true")
    args = parser.parse_args()

    data = analyze()

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        files = data["files"]
        print()
        print("=" * 60)
        print(" 🔥 CODE CHURN ANALYZER")
        print("=" * 60)
        print(f"   Files analyzed: {data['total_files']}")
        print(f"   Total changes:  {data['total_changes']}")
        print(f"   Hotspots:       {data['hotspots']} (score > 2)")
        print()
        print(f"   {'File':<35s} {'Chg':>4s} {'Lines':>6s} {'Score':>7s}")
        print(f"   {'-'*54}")

        for fname, changes, lines, score in files[:20]:
            if score > 2:
                icon = "🔥" if score > 10 else "🟡"
            elif score > 0:
                icon = "🟢"
            else:
                icon = "⚪"
            print(f"   {icon} {fname:<32s} {changes:4d} {lines:6d} {score:7.1f}")

        print()
        if data["hotspots"] > 0:
            print(f"   ⚠️  {data['hotspots']} hotspots — overweeg refactoring")
        else:
            print(f"   ✅ Geen hotspots — code is stabiel")


if __name__ == "__main__":
    main()
