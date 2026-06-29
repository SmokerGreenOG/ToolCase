from __future__ import annotations

__maker__ = "SmokerGreenOG"
import _protect

import argparse
import sys

from .core.engine import analyze_apk


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ToolCase APK Reverse Engineering Suite")
    parser.add_argument("--apk", required=True, help="Path to APK file")
    parser.add_argument("--out", required=True, help="Output report directory")
    parser.add_argument("--jadx", action="store_true", help="Run JADX if available on PATH")
    parser.add_argument("--apktool", action="store_true", help="Run apktool if available on PATH")
    args = parser.parse_args(argv)

    try:
        result = analyze_apk(args.apk, args.out, use_jadx=args.jadx, use_apktool=args.apktool)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(result["summary"])
    print(f"Risk score: {result['risk']['score']}/100")
    print(f"JSON report: {result['artifacts']['json_report']}")
    print(f"HTML report: {result['artifacts']['html_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
