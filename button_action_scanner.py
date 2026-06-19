#!/usr/bin/env python3
"""
button_action_scanner.py — Find UI elements with missing or placeholder actions.

Scans frontend source files for buttons, forms, links, and menu-items that lack
real interactivity. Detects:

  - buttons without onClick handlers
  - buttons with empty onClick handlers
  - forms without onSubmit / submit handlers
  - menu-items without action handlers
  - disabled buttons without an accompanying reason/title
  - anchor links with href="#"
  - placeholder/empty event handlers (e.g. onClick={() => {}})
  - handlers that do nothing but console.log (placeholder debugging stubs)

Gebruik:
    python button_action_scanner.py <path>
    python button_action_scanner.py <path> --json
    python button_action_scanner.py <path> --threshold 5
"""

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = frozenset({
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    "build", "dist", ".next", "coverage", ".svelte-kit",
})

TARGET_EXTENSIONS = frozenset({".tsx", ".ts", ".jsx", ".js", ".vue", ".svelte", ".html"})

# ---------------------------------------------------------------------------
# Detection patterns (compiled once)
# ---------------------------------------------------------------------------

# Attribute extraction (captures attribute="...", attribute='...', attribute={...}, attribute)
# Uses a brace-matching branch for JSX expressions like onClick={() => { handler() }}
# so nested {} are handled correctly.
_ATTR_DQ = r'"([^"]*)"'           # double-quoted
_ATTR_SQ = r"'([^']*)'"          # single-quoted
_ATTR_BRACE = r"\{((?:[^{}]|\{[^{}]*\})*)\}"  # JSX brace expression (one level deep)
ATTR_RE = re.compile(
    r"(\w[\w.-]*)\s*=\s*(?:"
    + _ATTR_DQ + "|" + _ATTR_SQ + "|" + _ATTR_BRACE
    + r")|(\b\w[\w.-]*)(?=\s|/?>|$)",
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Pattern checks
# ---------------------------------------------------------------------------

EMPTY_HANDLER_BODIES = re.compile(
    r'\{\s*(?:/\*[\s\S]*?\*/)?\s*\}',
    re.DOTALL,
)

CONSOLE_LOG_ONLY = re.compile(
    r'console\.(?:log|debug|info|warn|error)\s*\([^)]*\)',
)

# Callback expressions that look like function/arrow stubs
# Matches () => {}, () => { }, function() {}, function() { }
PLACEHOLDER_STUB = re.compile(
    r'(?:\([^)]*\)\s*=>\s*\{\s*\}|function\s*\([^)]*\)\s*\{\s*\})',
)

# ---------------------------------------------------------------------------
# Scanner logic
# ---------------------------------------------------------------------------


def extract_attributes(tag_content: str) -> dict[str, str]:
    """Extract all attributes and their raw values from a tag body.

    Returns a dict where the *presence* of a key means the attribute was
    explicitly written on the tag.  Missing keys == attribute not present.
    Boolean attributes (e.g. ``disabled``) map to ``"true"``.
    """
    attrs: dict[str, str] = {}
    for match in ATTR_RE.finditer(tag_content):
        name = match.group(1) or match.group(5)
        if not name:
            continue
        name_lower = name.lower()
        # Value: group 2 (dq), 3 (sq), 4 (brace), or empty string (boolean attr)
        value = match.group(2) or match.group(3) or match.group(4) or ""
        # For boolean HTML attributes without a value, mark as "true"
        if match.group(5):  # bare attribute like `disabled`
            attrs[name_lower] = "true"
        else:
            attrs[name_lower] = value
    return attrs


def is_console_log_only(value: str) -> bool:
    """Check if an event handler value only contains console.log calls."""
    # Strip outer braces if present
    inner = value.strip()
    if inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1].strip()
    # Remove the function signature part
    no_sig = re.sub(r'(?:\([^)]*\)\s*=>|function\s*\([^)]*\))', "", inner).strip()
    # Check if only console statements remain, possibly with semicolons
    calls = CONSOLE_LOG_ONLY.findall(no_sig)
    remaining = CONSOLE_LOG_ONLY.sub("", no_sig).strip().strip(";").strip()
    return bool(calls) and not remaining


def is_placeholder_handler(value: str) -> bool:
    """Check if the handler is an empty stub or just a comment + empty body."""
    inner = value.strip()
    if inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1].strip()
    # Remove outer function/arrow wrapper, then check for empty body
    stripped = re.sub(r'(?:\([^)]*\)\s*=>|function\s*\([^)]*\)\s*)', "", inner).strip()
    if EMPTY_HANDLER_BODIES.fullmatch(stripped):
        return True
    # Also check if the whole value is just () => {} or similar
    if PLACEHOLDER_STUB.fullmatch(value.strip()):
        return True
    return False


def _find_tags(content: str):
    """Yield (tag_name, tag_body, line_no) for each opening HTML/JSX tag.

    Walks the content character-by-character, counting braces so that
    ``>`` characters inside JSX expressions (e.g. ``onClick={() => {}}``)
    are correctly ignored.
    """
    i = 0
    length = len(content)
    while i < length:
        # Look for '<' followed by a tag name character
        if content[i] != "<":
            i += 1
            continue
        if i + 1 >= length:
            break

        # Skip comments, CDATA, DOCTYPE
        if content[i : i + 4] == "<!--":
            end = content.find("-->", i + 4)
            i = end + 3 if end != -1 else length
            continue
        if content[i : i + 3] in ("<%", "<?", "<!"):
            i += 1
            continue

        next_ch = content[i + 1]
        if not next_ch.isalnum() and next_ch not in ("_", ":"):
            i += 1
            continue

        # Extract tag name
        j = i + 1
        while j < length and (content[j].isalnum() or content[j] in "._:-"):
            j += 1
        tag_name = content[i + 1 : j]

        # Skip self-closing (e.g. <br/>) and closing tags (e.g. </div>)
        if tag_name.startswith("/"):
            i = j
            continue

        # Now walk the tag body, handling braces, quotes, and backticks
        brace_depth = 0
        in_dq = False
        in_sq = False
        in_bt = False  # backtick (template literal)
        k = j
        closed = False
        while k < length:
            ch = content[k]

            # Track string delimiters (skip content inside them)
            if ch == '"' and not in_sq and not in_bt:
                in_dq = not in_dq
                k += 1
                continue
            if ch == "'" and not in_dq and not in_bt:
                in_sq = not in_sq
                k += 1
                continue
            if ch == "`" and not in_dq and not in_sq:
                in_bt = not in_bt
                k += 1
                continue

            # Escape sequence inside string — skip next char
            if ch == "\\" and (in_dq or in_sq or in_bt):
                k += 2
                continue

            if not in_dq and not in_sq and not in_bt:
                if ch == "{":
                    brace_depth += 1
                elif ch == "}":
                    brace_depth -= 1
                elif ch == ">" and brace_depth == 0:
                    # This is the real closing >
                    tag_body = content[j:k]
                    line_no = content[:i].count("\n") + 1
                    yield tag_name.strip(), tag_body.strip(), line_no
                    closed = True
                    k += 1
                    break
                elif ch == "/" and k + 1 < length and content[k + 1] == ">" and brace_depth == 0:
                    # Self-closing tag like <br />
                    tag_body = content[j:k]
                    line_no = content[:i].count("\n") + 1
                    yield tag_name.strip(), tag_body.strip(), line_no
                    closed = True
                    k += 2
                    break

            k += 1

        if not closed:
            # Unclosed tag — move past '<'
            i = j
        else:
            i = k


def scan_file(filepath: Path) -> list[dict]:
    """Scan a single file for action-less UI elements."""
    findings: list[dict] = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return findings

    lines = content.split("\n")

    for tag_name, tag_body, line_no in _find_tags(content):
        attrs = extract_attributes(tag_body)
        tag_lower = tag_name.lower()

        # ---- Button checks ----
        if tag_lower == "button" or tag_name.endswith("Button"):
            # Get onClick value (empty string if attribute not present)
            onclick = attrs.get("onclick", attrs.get("on-click", attrs.get("v-on:click", "")))
            has_onclick_attr = "onclick" in attrs or "on-click" in attrs or "v-on:click" in attrs
            is_disabled = "disabled" in attrs

            if has_onclick_attr and onclick.strip() in ("", "{}", "{ }"):
                findings.append({
                    "type": "button_empty_onclick",
                    "severity": "warning",
                    "file": str(filepath),
                    "line": line_no,
                    "tag": tag_name,
                    "message": f"<{tag_name}> has an empty onClick handler",
                    "snippet": _snippet(lines, line_no),
                })
            elif not has_onclick_attr and not is_disabled:
                findings.append({
                    "type": "button_no_onclick",
                    "severity": "warning",
                    "file": str(filepath),
                    "line": line_no,
                    "tag": tag_name,
                    "message": f"<{tag_name}> has no onClick handler",
                    "snippet": _snippet(lines, line_no),
                })
            elif has_onclick_attr and is_placeholder_handler(onclick):
                findings.append({
                    "type": "button_placeholder_handler",
                    "severity": "info",
                    "file": str(filepath),
                    "line": line_no,
                    "tag": tag_name,
                    "message": f"<{tag_name}> has a placeholder onClick handler (empty stub)",
                    "snippet": _snippet(lines, line_no),
                })
            elif has_onclick_attr and is_console_log_only(onclick):
                findings.append({
                    "type": "button_console_log_handler",
                    "severity": "info",
                    "file": str(filepath),
                    "line": line_no,
                    "tag": tag_name,
                    "message": f"<{tag_name}> onClick only calls console.log",
                    "snippet": _snippet(lines, line_no),
                })

            if is_disabled and "title" not in attrs and "aria-label" not in attrs:
                findings.append({
                    "type": "disabled_button_no_reason",
                    "severity": "info",
                    "file": str(filepath),
                    "line": line_no,
                    "tag": tag_name,
                    "message": f"<{tag_name}> is disabled but has no title or aria-label explaining why",
                    "snippet": _snippet(lines, line_no),
                })

        # ---- Anchor / Link checks ----
        if tag_lower in ("a", "link", "linkbutton") or tag_name.endswith("Link"):
            href = attrs.get("href", attrs.get("to", attrs.get("link", "")))
            has_href_attr = "href" in attrs or "to" in attrs or "link" in attrs
            has_onclick_attr = "onclick" in attrs or "on-click" in attrs
            onclick = attrs.get("onclick", attrs.get("on-click", ""))

            if has_href_attr and href.strip() == "#" and not has_onclick_attr:
                findings.append({
                    "type": "link_href_hash",
                    "severity": "warning",
                    "file": str(filepath),
                    "line": line_no,
                    "tag": tag_name,
                    "message": f"<{tag_name}> has href=\"#\" with no onClick",
                    "snippet": _snippet(lines, line_no),
                })
            elif has_href_attr and href.strip() == "#" and has_onclick_attr and is_placeholder_handler(onclick):
                findings.append({
                    "type": "link_placeholder",
                    "severity": "info",
                    "file": str(filepath),
                    "line": line_no,
                    "tag": tag_name,
                    "message": f"<{tag_name}> has href=\"#\" with a placeholder onClick",
                    "snippet": _snippet(lines, line_no),
                })

        # ---- Form checks ----
        if tag_lower == "form" or tag_name.endswith("Form"):
            onsubmit = attrs.get("onsubmit", attrs.get("on-submit", attrs.get("@submit", "")))
            action = attrs.get("action", "")
            has_submit_attr = "onsubmit" in attrs or "on-submit" in attrs or "@submit" in attrs
            has_action_attr = "action" in attrs
            if not has_submit_attr and not has_action_attr:
                findings.append({
                    "type": "form_no_submit",
                    "severity": "warning",
                    "file": str(filepath),
                    "line": line_no,
                    "tag": tag_name,
                    "message": f"<{tag_name}> has no onSubmit handler and no action attribute",
                    "snippet": _snippet(lines, line_no),
                })
            elif has_submit_attr and is_placeholder_handler(onsubmit):
                findings.append({
                    "type": "form_placeholder_submit",
                    "severity": "info",
                    "file": str(filepath),
                    "line": line_no,
                    "tag": tag_name,
                    "message": f"<{tag_name}> has a placeholder onSubmit handler",
                    "snippet": _snippet(lines, line_no),
                })

        # ---- Menu-item checks ----
        if "menu" in tag_lower or "menuitem" in tag_lower or tag_lower in (
            "menuitem", "menu-item", "listitem", "li",
        ):
            click_attrs = (
                attrs.get("onclick", ""),
                attrs.get("@click", ""),
                attrs.get("v-on:click", ""),
                attrs.get("action", ""),
                attrs.get("command", ""),
                attrs.get("onactivate", ""),
            )
            has_action = any(a.strip() for a in click_attrs)
            has_href = attrs.get("href", "").strip() not in ("", "#")

            if not has_action and not has_href:
                findings.append({
                    "type": "menu_item_no_action",
                    "severity": "warning",
                    "file": str(filepath),
                    "line": line_no,
                    "tag": tag_name,
                    "message": f"<{tag_name}> menu-item has no action handler",
                    "snippet": _snippet(lines, line_no),
                })
            elif has_action:
                action_val = next((a for a in click_attrs if a.strip()), "")
                if is_placeholder_handler(action_val):
                    findings.append({
                        "type": "menu_item_placeholder",
                        "severity": "info",
                        "file": str(filepath),
                        "line": line_no,
                        "tag": tag_name,
                        "message": f"<{tag_name}> menu-item has a placeholder action",
                        "snippet": _snippet(lines, line_no),
                    })

    return findings


def _snippet(lines: list[str], line_no: int, context: int = 1) -> str:
    """Extract a short code snippet around the given 1-indexed line."""
    idx = line_no - 1
    start = max(0, idx - context)
    end = min(len(lines), idx + context + 1)
    snippet_lines = []
    for i in range(start, end):
        prefix = ">" if i == idx else " "
        snippet_lines.append(f"{prefix} {i + 1}: {lines[i]}")
    return "\n".join(snippet_lines)


def collect_files(root: Path) -> list[Path]:
    """Recursively collect all target source files under *root*."""
    files: list[Path] = []
    try:
        for entry in root.rglob("*"):
            if entry.is_dir() and entry.name in EXCLUDE_DIRS:
                continue
            if entry.is_file() and entry.suffix in TARGET_EXTENSIONS:
                files.append(entry)
    except PermissionError:
        pass
    return files


def summarize(findings: list[dict]) -> dict:
    """Group findings by type and produce counts + per-file summaries."""
    by_type: dict[str, list[dict]] = {}
    for f in findings:
        by_type.setdefault(f["type"], []).append(f)

    by_file: dict[str, list[dict]] = {}
    for f in findings:
        by_file.setdefault(f["file"], []).append(f)

    return {
        "total": len(findings),
        "by_type": {t: len(v) for t, v in sorted(by_type.items())},
        "files_affected": len(by_file),
        "details": findings,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan frontend files for buttons, forms, and menu-items with no real action.",
        epilog="Exit codes: 0 = no issues, 1 = issues found, 2 = error",
    )
    parser.add_argument("path", nargs="?", default=".", help="File or directory to scan")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (machine-readable)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=0,
        help="Minimum number of issues to exit with code 1 (default: 0)",
    )
    parser.add_argument(
        "--min-severity",
        choices=["info", "warning", "error"],
        default="info",
        help="Minimum severity level to report (default: info)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Additional directory names to exclude (can be used multiple times)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    target = Path(args.path).resolve()
    if not target.exists():
        print(f"Error: path does not exist: {target}", file=sys.stderr)
        return 2

    # Merge user-supplied excludes
    global EXCLUDE_DIRS
    EXCLUDE_DIRS = EXCLUDE_DIRS | frozenset(args.exclude)

    severity_order = {"info": 0, "warning": 1, "error": 2}
    min_level = severity_order.get(args.min_severity, 0)

    all_findings: list[dict] = []

    if target.is_file():
        files = [target] if target.suffix in TARGET_EXTENSIONS else []
    else:
        files = collect_files(target)

    if not files:
        print(f"No target source files found in {target}", file=sys.stderr)
        return 0

    for fp in files:
        findings = scan_file(fp)
        for f in findings:
            f_level = severity_order.get(f.get("severity", "info"), 0)
            if f_level >= min_level:
                all_findings.append(f)

    result = summarize(all_findings)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_human(result)

    if result["total"] > args.threshold:
        return 1
    return 0


def _print_human(result: dict) -> None:
    """Print a human-readable summary."""
    print(f"\n{'='*60}")
    print(f"  Button Action Scanner — Summary")
    print(f"{'='*60}")
    print(f"  Total issues found:  {result['total']}")
    print(f"  Files affected:      {result['files_affected']}")
    print(f"{'='*60}")

    if result["by_type"]:
        print(f"\n  Breakdown by type:")
        for t, count in result["by_type"].items():
            label = t.replace("_", " ").title()
            print(f"    {label:<35s}  {count}")
        print()

    # Print details grouped by file
    by_file: dict[str, list[dict]] = {}
    for f in result["details"]:
        by_file.setdefault(f["file"], []).append(f)

    if by_file:
        print(f"{'─'*60}")
        for filepath, issues in sorted(by_file.items()):
            rel = Path(filepath).resolve()
            print(f"\n  📄  {rel}")
            for issue in issues:
                sev_icon = {"info": "ℹ", "warning": "⚠", "error": "✖"}.get(
                    issue.get("severity", "info"), "•"
                )
                print(f"    {sev_icon} L{issue['line']:>5d}  [{issue['type']}]")
                print(f"           {issue['message']}")
                if issue.get("snippet"):
                    for snippet_line in issue["snippet"].split("\n"):
                        print(f"           {snippet_line}")
        print(f"\n{'─'*60}")
        print()


if __name__ == "__main__":
    sys.exit(main())
