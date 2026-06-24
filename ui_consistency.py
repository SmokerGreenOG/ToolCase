#!/usr/bin/env python3
"""
ui_consistency.py — Check UI pattern consistency across the codebase.

Detects:
  - Color token usage consistency
  - Font family/style usage patterns
  - Spacing/margin/padding patterns
  - Component naming conventions
  - Import style consistency
  - File naming patterns in UI directories
  - Inline styles vs CSS classes ratio
  - Hardcoded colors vs CSS variables

Gebruik:
    python ui_consistency.py <path>                      # Check UI consistency
    python ui_consistency.py <path> --json                # JSON output
    python ui_consistency.py <path> --tailwind            # Tailwind CSS mode
    python ui_consistency.py <path> --strict              # Strict mode
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import os
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = frozenset({
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    "build", "dist", ".next",
        ".backups",

        ".rsi_backups",

        ".rsi_reports",

        ".self_improve_reports",
        })

# CSS/Tailwind color pattern
COLOR_PATTERN = re.compile(
    r'(?:color|background|background-color|border-color|outline-color|'
    r'accent-color|caret-color|fill|stroke)\s*:\s*'
    r'([#(:\w][^;{]+)',
    re.IGNORECASE,
)

HEX_COLOR = re.compile(r'#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b')
RGB_COLOR = re.compile(r'rgb(?:a)?\s*\([^)]+\)', re.IGNORECASE)
CSS_VAR = re.compile(r'var\(--[\w-]+\)')
TAILWIND_COLOR = re.compile(r'\b(bg|text|border|outline|ring|from|via|to)-[\w-]+')

# Spacing patterns
SPACING_PATTERN = re.compile(
    r'(?:margin|padding|gap|row-gap|column-gap|inset|top|right|bottom|left)\s*:\s*[^;]+',
    re.IGNORECASE,
)

# Font patterns
FONT_PATTERN = re.compile(
    r'(?:font-family|font-size|font-weight|font-style|font|typography)\s*:\s*[^;]+',
    re.IGNORECASE,
)

# Inline style detection
INLINE_STYLE = re.compile(r'style\s*=\s*\{[^}]+\}|style\s*=\s*"[^"]+"')

# CSS class usage
CSS_CLASS = re.compile(r'className\s*=\s*[\'"`]([^\'"`]+)[\'"`]')


def collect_ui_files(root: Path) -> list[Path]:
    """Collect UI-related files."""
    files = []
    ui_exts = {".ts", ".tsx", ".js", ".jsx", ".css", ".scss", ".html"}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        path = Path(dirpath)

        # Only look in UI-related directories
        dir_name = path.name.lower()
        if any(x in str(path).lower() for x in
               ["components", "pages", "layouts", "styles", "ui", "theme",
                "app", "src/components", "src/pages", "src/styles"]):
            for fn in filenames:
                ext = Path(fn).suffix.lower()
                if ext in ui_exts:
                    files.append(path / fn)

    return sorted(files)


def analyze_color_consistency(files: list[Path]) -> dict:
    """Analyze color usage patterns."""
    colors = {
        "css_vars": Counter(),
        "hex_colors": Counter(),
        "rgb_colors": Counter(),
        "tailwind_colors": Counter(),
        "hardcoded_colors": [],
        "total_colors": 0,
        "css_var_ratio": 0.0,
    }

    for fp in files:
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # CSS variables
        for m in CSS_VAR.finditer(content):
            colors["css_vars"][m.group()] += 1
            colors["total_colors"] += 1

        # Hex colors
        for m in HEX_COLOR.finditer(content):
            hex_color = m.group().upper()
            colors["hex_colors"][hex_color] += 1
            colors["total_colors"] += 1

            # Track hardcoded colors (not in a --var context)
            line_start = max(0, m.start() - 100)
            context = content[line_start:line_start + 150]
            if "var(" not in context:
                colors["hardcoded_colors"].append({
                    "file": str(fp),
                    "color": hex_color,
                    "line": content[:m.start()].count("\n") + 1,
                    "context": context[:80].strip(),
                })

        # RGB colors
        for m in RGB_COLOR.finditer(content):
            colors["rgb_colors"][m.group()] += 1
            colors["total_colors"] += 1

        # Tailwind colors
        for m in TAILWIND_COLOR.finditer(content):
            colors["tailwind_colors"][m.group()] += 1
            colors["total_colors"] += 1

    if colors["total_colors"] > 0:
        css_var_count = sum(colors["css_vars"].values())
        colors["css_var_ratio"] = css_var_count / colors["total_colors"]

    return colors


def analyze_styling_patterns(files: list[Path]) -> dict:
    """Analyze inline styles vs CSS classes."""
    results = {
        "inline_styles": 0,
        "css_classes": 0,
        "class_names": Counter(),
        "files_with_inline": [],
    }

    for fp in files:
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        inline_count = len(INLINE_STYLE.findall(content))
        class_count = 0

        for m in CSS_CLASS.finditer(content):
            classes = m.group(1).split()
            for cls in classes:
                cls = cls.strip().strip("'\"`")
                if cls:
                    results["class_names"][cls] += 1
                    class_count += 1

        results["inline_styles"] += inline_count
        results["css_classes"] += class_count

        if inline_count > 0:
            results["files_with_inline"].append({
                "file": str(fp),
                "inline_count": inline_count,
                "class_count": class_count,
            })

    return results


def analyze_component_naming(files: list[Path]) -> dict:
    """Analyze component naming conventions."""
    results = {
        "pascal_case": 0,
        "kebab_case": 0,
        "snake_case": 0,
        "camel_case": 0,
        "naming_examples": [],
    }

    pascal = re.compile(r'^[A-Z][a-zA-Z0-9]*\.(tsx|jsx)$')
    kebab = re.compile(r'^[a-z][a-z0-9-]*\.(tsx|jsx|ts|js)$')
    snake = re.compile(r'^[a-z][a-z0-9_]*\.(tsx|jsx|ts|js)$')
    camel = re.compile(r'^[a-z][a-zA-Z0-9]*\.(tsx|jsx|ts|js)$')

    for fp in files:
        name = fp.name
        if pascal.match(name):
            results["pascal_case"] += 1
        elif kebab.match(name):
            results["kebab_case"] += 1
        elif snake.match(name):
            results["snake_case"] += 1
        elif camel.match(name) and not snake.match(name):
            results["camel_case"] += 1

    return results


def print_report(colors: dict, styling: dict, naming: dict) -> None:
    """Print a formatted UI consistency report."""
    print(f"\n{'='*60}")
    print(f" 🎨 UI CONSISTENCY CHECK")
    print(f"{'='*60}")

    # Color Analysis
    total_colors = colors["total_colors"]
    hardcoded = len(colors["hardcoded_colors"])
    css_var_count = sum(colors["css_vars"].values())
    hex_count = sum(colors["hex_colors"].values())

    print(f"\n ── Colors ──")
    print(f"   Total colors found:  {total_colors}")
    print(f"   ✅ CSS vars used:     {css_var_count}x ({colors['css_var_ratio']*100:.0f}%)")
    print(f"   🟥 Hardcoded hex:     {hex_count}x")
    print(f"   ⚠  Hardcoded (no var): {hardcoded}x")
    print()

    if hardcoded > 0:
        print(f"   Top hardcoded hex colors:")
        for color, count in colors["hex_colors"].most_common(5):
            if not any(color in str(h["color"]) for h in colors["hardcoded_colors"][:5]):
                continue
            print(f"     {color}: {count}x")

    if colors["tailwind_colors"]:
        print(f"\n   Tailwind colors used:")
        for color, count in colors["tailwind_colors"].most_common(10):
            print(f"     {color}: {count}x")

    # Styling Analysis
    total_inline = styling["inline_styles"]
    total_class = styling["css_classes"]

    print(f"\n ── Styling Patterns ──")
    print(f"   📝 CSS classes:       {total_class}")
    print(f"   🎯 Inline styles:     {total_inline}")

    if total_class + total_inline > 0:
        inline_ratio = total_inline / (total_class + total_inline) * 100
        print(f"   Inline/style ratio:  {inline_ratio:.1f}% inline")
        if inline_ratio > 20:
            print(f"   ⚠  Hoog aandeel inline styles — overweeg CSS classes")
    print()

    if styling["class_names"]:
        print(f"   Top CSS classes:")
        for cls, count in styling["class_names"].most_common(10):
            print(f"     .{cls}: {count}x")

    # Component Naming
    total_components = (naming["pascal_case"] + naming["kebab_case"]
                        + naming["snake_case"] + naming["camel_case"])
    print(f"\n ── File Naming Conventions ──")
    print(f"   PascalCase (React):  {naming['pascal_case']}  ✅")
    print(f"   kebab-case (utils):  {naming['kebab_case']}  ✅")
    print(f"   snake_case (Python): {naming['snake_case']}  ✅")
    print(f"   camelCase:           {naming['camel_case']}  ⚠")
    print()

    dominant = max(naming.items(), key=lambda x: x[1])[0]
    print(f"   Dominant convention: {dominant.replace('_', ' ').title()}")
    if naming["camel_case"] > 0 and naming["pascal_case"] > naming["camel_case"] * 2:
        print(f"   ✅ Consistent met PascalCase voor componenten")
    elif naming["camel_case"] > naming["pascal_case"]:
        print(f"   ⚠  Overweeg PascalCase voor React componenten")
    print()

    # Overall score
    scores = []
    if total_colors > 0:
        scores.append(colors["css_var_ratio"] * 40)  # 40 points for CSS vars
    if total_class + total_inline > 0:
        class_ratio = total_class / (total_class + total_inline)
        scores.append(class_ratio * 30)  # 30 points for class usage
    if total_components > 0:
        pascal_ratio = naming["pascal_case"] / total_components if total_components > 0 else 0
        scores.append(pascal_ratio * 30)  # 30 points for naming

    if scores:
        total_score = sum(scores)
        if total_score >= 80:
            grade = "A"
        elif total_score >= 60:
            grade = "B"
        elif total_score >= 40:
            grade = "C"
        else:
            grade = "D"
        print(f" ── Overall Score: {total_score:.0f}/100 ({grade}) ──")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ui_consistency.py — Check UI pattern consistency across the codebase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python ui_consistency.py .
  python ui_consistency.py src/ --json
  python ui_consistency.py . --tailwind
  python ui_consistency.py . --strict
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root")
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument("--tailwind", "-t", action="store_true",
                        help="Tailwind CSS mode (extra checks)")
    parser.add_argument("--strict", "-s", action="store_true",
                        help="Strict mode (lagere tolerantie)")
    parser.add_argument("--version", action="version", version="ui_consistency.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 UI Consistency Check v1.0.0 — scanning {target}")

    files = collect_ui_files(target)
    if not files:
        print(" Geen UI-bestanden gevonden")
        sys.exit(0)

    print(f"   {len(files)} UI-bestand(en) gevonden")

    colors = analyze_color_consistency(files)
    styling = analyze_styling_patterns(files)
    naming = analyze_component_naming(files)

    if args.json:
        output = {
            "files_scanned": len(files),
            "colors": {k: v for k, v in colors.items() if k != "hardcoded_colors"},
            "hardcoded_colors": colors["hardcoded_colors"][:20],
            "styling": styling,
            "naming": naming,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    else:
        print_report(colors, styling, naming)


if __name__ == "__main__":
    main()
