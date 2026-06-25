#!/usr/bin/env python3
"""
complexity.py — Cyclomatic complexity & cognitive load meter.

Analyseert Python, TypeScript en Rust bestanden op:
  - Cyclomatische complexiteit (McCabe) per functie
  - Cognitieve load per functie (geneste ifs, boolean operatoren tellen zwaarder)
  - Samenvatting: top 5 meest complexe functies, gemiddelden, bestandsstatistieken

Gebruik:
  python complexity.py <file>
  python complexity.py <path> --recursive
  python complexity.py <path> --json
  python complexity.py <path> --threshold 10

Gebruikt enkel stdlib (re, json, sys, os, argparse).
"""

__maker__ = "SmokerGreenOG"

import _protect
import re
import json
import sys
import os
import argparse
from collections import defaultdict

# Ensure UTF-8 output on all platforms (Windows cp1252 can't handle emoji/unicode)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────
# PATRONEN per taal
# ─────────────────────────────────────────────

PATTERNS = {
    "py": {
        "function_start": re.compile(r"^(\s*)def\s+(\w+)\s*\("),
        "function_call": re.compile(r"^\s*(\w+)\s*\(", re.MULTILINE),
        "decision_points": {
            re.compile(r"\bif\b"),  # if
            re.compile(r"\belif\b"),  # elif
            re.compile(r"\belse\b"),  # else
            re.compile(r"\bfor\b"),  # for
            re.compile(r"\bwhile\b"),  # while
            re.compile(r"\band\b"),  # and
            re.compile(r"\bor\b"),  # or
            re.compile(r"\bexcept\b"),  # except
            re.compile(r"\btry\b"),  # try counts as 0, but except is 1
        },
        "boolean_ops": {
            re.compile(r"\band\b"),
            re.compile(r"\bor\b"),
        },
        "nested_increment": {
            re.compile(r"\bif\b"),
            re.compile(r"\bfor\b"),
            re.compile(r"\bwhile\b"),
            re.compile(r"\btry\b"),
        },
        "comment": re.compile(r"^\s*#"),
        "string_literal": re.compile(r'"""|\'\'\'|"|\''),
    },
    "ts": {
        "function_start": re.compile(
            r"(?:^|\s)"  # start of line or whitespace
            r"(?:"
            r"(?:public|private|protected|static|async|export|default|\s)*\bfunction\s+(\w+)\s*\("
            r"|"
            r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*(?::[^=]+)?\s*=>"
            r"|"
            r"(\w+)\s*\([^)]*\)\s*\{"  # methodName() {
            r")"
        ),
        "decision_points": {
            re.compile(r"\bif\b"),
            re.compile(r"\belse\s+if\b"),
            re.compile(r"\belse\b"),
            re.compile(r"\bfor\b"),
            re.compile(r"\bwhile\b"),
            re.compile(r"\bcatch\b"),
            re.compile(r"\bswitch\b"),
            re.compile(r"\bcase\b"),
            re.compile(r"\?\s*[^?]"),  # ternary ? (not nullish ??)
            re.compile(r"\b&&\b"),
            re.compile(r"\b\|\|\b"),
        },
        "boolean_ops": {
            re.compile(r"\b&&\b"),
            re.compile(r"\b\|\|\b"),
        },
        "nested_increment": {
            re.compile(r"\bif\b"),
            re.compile(r"\bfor\b"),
            re.compile(r"\bwhile\b"),
            re.compile(r"\bcatch\b"),
            re.compile(r"\bfinally\b"),
        },
        "comment_single": re.compile(r"^\s*//"),
        "comment_multi_start": re.compile(r"/\*"),
    },
    "rs": {
        "function_start": re.compile(
            r"^(\s*)"  # leading whitespace
            r"(?:pub\s+)?"  # optional pub
            r"(?:unsafe\s+)?"  # optional unsafe
            r"(?:async\s+)?"  # optional async
            r"fn\s+"  # fn keyword
            r"(\w+)"  # function name
            r"\s*<"  # generic params start
            r"|"
            r"^(\s*)"  # leading whitespace
            r"(?:pub\s+)?"
            r"(?:unsafe\s+)?"
            r"(?:async\s+)?"
            r"fn\s+"  # fn keyword
            r"(\w+)"  # function name
            r"\s*\("  # paren start
        ),
        "decision_points": {
            re.compile(r"\bif\b"),
            re.compile(r"\belse\s+if\b"),
            re.compile(r"\belse\b"),
            re.compile(r"\bfor\b"),
            re.compile(r"\bwhile\b"),
            re.compile(r"\bmatch\b"),
            re.compile(r"\bcatch\b"),
            re.compile(r"\b&&\b"),
            re.compile(r"\b\|\|\b"),
        },
        "boolean_ops": {
            re.compile(r"\b&&\b"),
            re.compile(r"\b\|\|\b"),
        },
        "nested_increment": {
            re.compile(r"\bif\b"),
            re.compile(r"\bfor\b"),
            re.compile(r"\bwhile\b"),
            re.compile(r"\bmatch\b"),
            re.compile(r"\bloop\b"),
        },
        "comment_single": re.compile(r"^\s*//"),
        "comment_multi_start": re.compile(r"/\*"),
    },
}


def detect_language(filepath: str) -> str:
    """Detecteer taal op basis van extensie."""
    ext = os.path.splitext(filepath)[1].lower()
    mapping = {".py": "py", ".ts": "ts", ".rs": "rs"}
    lang = mapping.get(ext)
    if not lang:
        raise ValueError(f"Onbekende extensie: {ext}. Ondersteund: .py, .ts, .rs")
    return lang


def read_file(filepath: str) -> list[str]:
    """Lees bestand, retourneer lijst met regels."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.readlines()
    except Exception as e:
        print(f"Fout bij lezen {filepath}: {e}", file=sys.stderr)
        sys.exit(1)


def find_functions_py(lines: list[str]) -> list[dict]:
    """Vind alle functies in Python code."""
    functions = []
    for i, line in enumerate(lines):
        m = PATTERNS["py"]["function_start"].match(line)
        if m:
            indent = len(m.group(1))
            name = m.group(2)
            # tel parameters
            paren_start = line.index("(")
            paren_end = _find_matching_paren(line, paren_start)
            params_str = line[paren_start + 1 : paren_end] if paren_end > paren_start else ""
            # ook multi-line parameters checken
            if paren_end == -1 or (paren_end > paren_start and ")" not in line[paren_start:]):
                # multi-line signature
                combined = line
                j = i + 1
                while j < len(lines) and "):" not in combined and ")" not in combined:
                    combined += lines[j]
                    j += 1
                if ")" in combined:
                    paren_end = combined.index(")", paren_start)
                    params_str = combined[paren_start + 1 : paren_end]
            params = [
                p for p in params_str.split(",") if p.strip() and p.strip() not in ("self", "cls")
            ]
            param_count = len(params)

            functions.append(
                {
                    "name": name,
                    "line": i + 1,
                    "indent": indent,
                    "end_line": None,
                    "params": param_count,
                }
            )
    return _compute_function_bodies(lines, functions, "py")


def find_functions_ts(lines: list[str]) -> list[dict]:
    """Vind alle functies in TypeScript code."""
    functions = []
    text = "\n".join(lines)
    for m in PATTERNS["ts"]["function_start"].finditer(text):
        name = m.group(1) or m.group(2) or m.group(3)
        if not name:
            continue
        # Bereken regelnummer
        line_no = text[: m.start()].count("\n") + 1

        # Tel parameters uit de match
        brace_pos = m.end()
        # Zoek de { die het function body start
        body_start = _find_body_start(text, brace_pos)

        functions.append(
            {
                "name": name,
                "line": line_no,
                "indent": 0,
                "end_line": None,
                "params": 0,
                "body_start": body_start,
            }
        )
    return _compute_function_bodies(lines, functions, "ts")


def find_functions_rs(lines: list[str]) -> list[dict]:
    """Vind alle functies in Rust code."""
    functions = []
    text = "\n".join(lines)

    # Eerste pattern: fn name<T>(...)
    pat1 = re.compile(
        r"^(\s*)"  # leading whitespace
        r"(?:pub\s+)?"  # optional pub
        r"(?:unsafe\s+)?"  # optional unsafe
        r"(?:async\s+)?"  # optional async
        r"fn\s+"  # fn keyword
        r"(\w+)"  # function name
        r"\s*<"  # generic params start
    )
    # Tweede pattern: fn name(...)
    pat2 = re.compile(
        r"^(\s*)"  # leading whitespace
        r"(?:pub\s+)?"
        r"(?:unsafe\s+)?"
        r"(?:async\s+)?"
        r"fn\s+"  # fn keyword
        r"(\w+)"  # function name
        r"\s*\("  # paren start
    )

    for m in pat1.finditer(text, re.MULTILINE):
        func = _make_rs_func(lines, text, m)
        if func:
            functions.append(func)
    # Vermijd duplicaten voor pat2
    existing_lines = {f["line"] for f in functions}
    for m in pat2.finditer(text, re.MULTILINE):
        line_no = text[: m.start()].count("\n") + 1
        if line_no in existing_lines:
            continue
        func = _make_rs_func(lines, text, m)
        if func:
            functions.append(func)

    return _compute_function_bodies(lines, functions, "rs")


def _make_rs_func(lines: list[str], text: str, m: re.Match) -> dict | None:
    """make rs func.

    Args:
        lines: Description.
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    name = m.group(2)
    if not name:
        return None
    line_no = text[: m.start()].count("\n") + 1
    # Zoek de { die het function body start
    # Rust fns kunnen een 'where' clause hebben, dus we moeten verder zoeken
    brace_pos = m.end()
    segment = text[m.start() :]
    # Skip generics en where clause
    depth = 0
    in_angle = False
    brace_idx = -1
    for idx, ch in enumerate(segment):
        if ch == "<":
            in_angle = True
        elif ch == ">":
            in_angle = False
        elif ch == "{" and not in_angle:
            brace_idx = m.start() + idx
            break
    if brace_idx == -1:
        return None

    return {
        "name": name,
        "line": line_no,
        "indent": len(m.group(1)),
        "end_line": None,
        "params": 0,
        "body_start": brace_idx,
    }


def _find_matching_paren(line: str, start: int) -> int:
    """Vind de sluitende haakjespositie in een string."""
    depth = 0
    for i in range(start, len(line)):
        if line[i] == "(":
            depth += 1
        elif line[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _find_body_start(text: str, pos: int) -> int:
    """Vind de { die het function body start na pos."""
    while pos < len(text) and text[pos] not in "{;":
        pos += 1
    if pos < len(text) and text[pos] == "{":
        return pos
    return -1


def _compute_function_bodies(lines: list[str], functions: list[dict], lang: str) -> list[dict]:
    """Bereken end_line voor elke functie op basis van indentatie of brace depth."""
    if lang == "py":
        return _compute_py_bodies(lines, functions)
    else:
        return _compute_brace_bodies(lines, functions)


def _compute_py_bodies(lines: list[str], functions: list[dict]) -> list[dict]:
    """Python: functie eindigt als indentatie terugkeert naar basisniveau."""
    functions_sorted = sorted(functions, key=lambda f: f["line"])
    result = []
    for idx, func in enumerate(functions_sorted):
        base_indent = func["indent"]
        start = func["line"]  # 1-based
        if idx + 1 < len(functions_sorted):
            next_func_line = functions_sorted[idx + 1]["line"]
            # Zoek de lege regel of minder indentatie voor de volgende functie
            end_line = _find_py_func_end(lines, base_indent, start, next_func_line)
        else:
            end_line = _find_py_func_end(lines, base_indent, start, len(lines) + 1)
        func["end_line"] = end_line
        result.append(func)

    # Terug naar originele volgorde
    func_lines = {f["line"]: f for f in functions}
    return [func_lines[f["line"]] for f in functions]


def _find_py_func_end(lines: list[str], base_indent: int, start: int, next_start: int) -> int:
    """Vind de laatste regel van een Python functie body."""
    end = start  # minstens 1 regel (def line zelf)
    for i in range(start, min(next_start - 1, len(lines))):
        if i == start:
            continue
        line = lines[i - 1]  # 0-based
        stripped = line.rstrip("\n").rstrip("\r")
        if not stripped:
            continue
        # Check indentatie
        indent = len(line) - len(line.lstrip())
        if indent <= base_indent and not stripped.startswith(("@", ")", "]", "}")):
            # Dit is waarschijnlijk een decorator of lege line
            # Als indent <= base_indent en geen decorator, dan stopt de functie
            if not stripped.startswith("@") and not stripped.startswith(")"):
                break
        end = i
    return end + 1  # 1-based


def _compute_brace_bodies(lines: list[str], functions: list[dict]) -> list[dict]:
    """TS/Rust: gebruik brace depth om functie bodies te vinden."""
    text = "\n".join(lines)
    result = []
    for func in functions:
        body_start = func.get("body_start", -1)
        if body_start == -1:
            func["end_line"] = func["line"]
            result.append(func)
            continue
        # Bereken brace depth vanaf body_start
        depth = 0
        end_pos = body_start
        for i in range(body_start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_pos = i
                    break
        # end_pos is de positie van de sluitende }
        body_ok = end_pos > body_start
        end_line = text[: end_pos + 1].count("\n") + 1 if body_ok else func["line"]
        func["end_line"] = end_line

        # Tel parameters op basis van signature tussen functienaam en first {
        sig_start = _find_sig_start(text, func["line"], None)
        if sig_start:
            has_brace = "{" in text[sig_start:]
            brace_end = text.index("{", sig_start) if has_brace else len(text)
            sig_text = text[sig_start:brace_end]
            paren_idx = sig_text.find("(")
            if paren_idx >= 0:
                close_paren = _find_matching_paren(sig_text, paren_idx)
                if close_paren >= 0:
                    params_str = sig_text[paren_idx + 1 : close_paren]
                    params_list = [
                        p
                        for p in params_str.split(",")
                        if p.strip() and not p.strip().startswith("//")
                    ]
                    func["params"] = len(params_list)
        result.append(func)
    return result


def _find_sig_start(text: str, line_no: int, lang: str) -> int:
    """Vind de startpositie van de functie signature in de tekst."""
    lines = text.split("\n")
    if 1 <= line_no <= len(lines):
        cumulative = 0
        for i in range(line_no - 1):
            cumulative += len(lines[i]) + 1
        return cumulative
    return 0


def _is_comment(line: str, lang: str) -> bool:
    """Check of een regel een comment is."""
    stripped = line.strip()
    if not stripped:
        return True
    for prefix in ("//", "#", "/*"):
        if stripped.startswith(prefix):
            return True
    if stripped.startswith("*") and not stripped.startswith("*/"):
        return True
    if stripped.startswith("--"):
        return True
    return False


def _remove_strings(line: str) -> str:
    """Verwijder string literals voor accurate parsing.
    Simpele implementatie — verwijdert quoted content."""
    # Python: triple quotes, single quotes, double quotes
    result = ""
    i = 0
    in_string = False
    string_char = None
    escape = False
    while i < len(line):
        ch = line[i]
        if escape:
            result += ch
            escape = False
            i += 1
            continue
        if ch == "\\":
            result += ch
            escape = True
            i += 1
            continue
        if in_string:
            if ch == string_char:
                in_string = False
            i += 1
            continue
        if ch in ('"', "'"):
            # Check voor triple quotes
            if line[i : i + 3] in ('"""', "'''"):
                in_string = True
                string_char = line[i : i + 3]
                i += 3
                continue
            in_string = True
            string_char = ch
            i += 1
            continue
        result += ch
        i += 1
    return result


def analyze_function(lines: list[str], func: dict, lang: str) -> dict:
    """Analyseer cyclomatische complexiteit en cognitieve load voor een functie."""
    start_line = func["line"] - 1  # 0-based
    end_line = min(func["end_line"], len(lines))  # 1-based -> exclusive
    if end_line <= start_line:
        end_line = start_line + 1

    body_lines = lines[start_line:end_line]
    body_text = "\n".join(body_lines)
    body_text_no_strings = _remove_strings(body_text)
    body_lines_no_strings = body_text_no_strings.split("\n")

    patterns = PATTERNS[lang]
    decision_points = patterns["decision_points"]
    boolean_ops = patterns["boolean_ops"]
    nested_increment = patterns.get("nested_increment", set())
    comment_patterns = []
    if "comment" in patterns:
        comment_patterns.append(patterns["comment"])
    if "comment_single" in patterns:
        comment_patterns.append(patterns["comment_single"])

    # Tel decision points
    cyclomatic = 1  # basis
    cognitive_load = 0
    nesting_depth = 0
    max_nesting = 0
    bool_op_count = 0

    # Track nesting depth per regel (door indentatie voor Python, brace count voor TS/RS)
    if lang == "py":
        base_indent = func["indent"]
        for line_idx, line in enumerate(body_lines_no_strings):
            stripped = line.strip()
            if not stripped:
                continue
            # Check comment
            is_comment_line = any(cp.match(line) for cp in comment_patterns)
            if is_comment_line:
                continue

            indent = len(line) - len(line.lstrip())
            relative_indent = max(0, indent - base_indent) // 4  # ~1 level per 4 spaces
            nesting_depth = relative_indent

            line_contrib = 0
            for dp_pattern in decision_points:
                if dp_pattern.search(stripped):
                    # Check dat het geen deel is van een identifier
                    cyclomatic += 1
                    # Cognitieve load: nesting * 1 voor elke geneste struct
                    if dp_pattern in nested_increment:
                        line_contrib += 1

            # Boolean operators dragen bij aan cognitieve load
            for bool_pat in boolean_ops:
                bool_matches = bool_pat.findall(stripped)
                bool_op_count += len(bool_matches)
                line_contrib += len(bool_matches)

            cognitive_load += line_contrib * (1 + nesting_depth)
            max_nesting = max(max_nesting, nesting_depth)
    else:
        # TS/RS: brace depth tracking
        brace_depth = 0
        for line_idx, line in enumerate(body_lines_no_strings):
            stripped = line.strip()
            if not stripped:
                continue
            # Check comment
            is_comment_line = any(cp.match(line) for cp in comment_patterns)
            if is_comment_line:
                continue

            # Update brace depth
            brace_depth += line.count("{") - line.count("}")
            brace_depth = max(0, brace_depth)

            # Eerste regel kan de { bevatten, skip die voor nesting
            line_contrib = 0
            for dp_pattern in decision_points:
                if dp_pattern.search(stripped):
                    cyclomatic += 1
                    if dp_pattern in nested_increment:
                        line_contrib += 1

            for bool_pat in boolean_ops:
                bool_matches = bool_pat.findall(stripped)
                bool_op_count += len(bool_matches)
                line_contrib += len(bool_matches)

            # Gebruik de brace depth van _voor_ deze regel voor nesting score
            depth_before = brace_depth + line.count("{") - line.count("}")
            if depth_before > 0:
                depth_before -= 1  # De huidige brace is voor deze structuur
            cognitive_load += line_contrib * (1 + max(0, depth_before))

            # Lege brace-depth reset niet volledig, maar we gebruiken de diepte netto
            # Eerste { op de functie regel telt niet als nesting
            line_braces_before = line.count("{")
            if line_braces_before > 0 and line_idx == 0:
                brace_depth = line_braces_before - 1

    # Aantal regels functie body (exclusief signature)
    loc = end_line - start_line

    return {
        "name": func["name"],
        "line": func["line"],
        "cyclomatic_complexity": cyclomatic,
        "params": func["params"],
        "loc": loc,
        "cognitive_load": cognitive_load,
        "max_nesting": max_nesting,
    }


def analyze_file(filepath: str) -> list[dict]:
    """Analyseer een bestand en retourneer functieresultaten."""
    lang = detect_language(filepath)
    lines = read_file(filepath)

    if lang == "py":
        functions = find_functions_py(lines)
    elif lang == "ts":
        functions = find_functions_ts(lines)
    else:  # rs
        functions = find_functions_rs(lines)

    results = []
    for func in functions:
        try:
            result = analyze_function(lines, func, lang)
            results.append(result)
        except Exception as e:
            print(f"Waarschuwing: fout bij analyseren van {func['name']}: {e}", file=sys.stderr)
    return results


def summary(results: list[dict]) -> dict:
    """Genereer samenvatting van alle functieresultaten."""
    if not results:
        return {
            "total_functions": 0,
            "average_cyclomatic": 0.0,
            "average_cognitive_load": 0.0,
            "top_5_complex": [],
            "functions": [],
        }

    avg_cyclo = sum(r["cyclomatic_complexity"] for r in results) / len(results)
    avg_cog = sum(r["cognitive_load"] for r in results) / len(results)

    sorted_by_cyclo = sorted(results, key=lambda r: r["cyclomatic_complexity"], reverse=True)
    top_5 = sorted_by_cyclo[:5]

    return {
        "total_functions": len(results),
        "average_cyclomatic": round(avg_cyclo, 2),
        "average_cognitive_load": round(avg_cog, 2),
        "top_5_complex": [
            {
                "name": f["name"],
                "line": f["line"],
                "cyclomatic_complexity": f["cyclomatic_complexity"],
                "cognitive_load": f["cognitive_load"],
            }
            for f in top_5
        ],
        "functions": results,
    }


def print_table(results: list[dict], threshold: int = 0) -> None:
    """Print een tabel met functiecomplexiteit."""
    if threshold:
        filtered = [r for r in results if r["cyclomatic_complexity"] >= threshold]
    else:
        filtered = results

    if not filtered:
        if threshold:
            print(f"Geen functies met cyclomatische complexiteit > {threshold}")
        else:
            print("Geen functies gevonden.")
        return

    # Header
    print(f"{'Functie':<30} {'Regel':<6} {'Cyclo':<7} {'Params':<7} {'LOC':<5} {'Cog.Load':<9}")
    print("-" * 70)

    for r in sorted(filtered, key=lambda x: x["cyclomatic_complexity"], reverse=True):
        print(
            f"{r['name']:<30} "
            f"{r['line']:<6} "
            f"{r['cyclomatic_complexity']:<7} "
            f"{r['params']:<7} "
            f"{r['loc']:<5} "
            f"{r['cognitive_load']:<9}"
        )


def print_summary(summ: dict, filepath: str) -> None:
    """Print een mooie samenvatting."""
    print(f"\n{'=' * 60}")
    print(f"  Samenvatting: {filepath}")
    print(f"{'=' * 60}")
    print(f"  Totaal functies:      {summ['total_functions']}")
    print(f"  Gem. cyclomatisch:    {summ['average_cyclomatic']}")
    print(f"  Gem. cognitive load:  {summ['average_cognitive_load']}")
    print(f"\n  Top 5 meest complexe functies:")
    print(f"  {'-' * 50}")
    for i, func in enumerate(summ["top_5_complex"], 1):
        print(
            f"  {i}. {func['name']:<25} "
            f"(regel {func['line']:<4}) "
            f"cyclo={func['cyclomatic_complexity']:<3} "
            f"cog={func['cognitive_load']:<3}"
        )
    print(f"{'=' * 60}\n")


def scan_recursive(path: str, threshold: int = 0, json_output: bool = False) -> None:
    """Scan een directory recursief voor .py, .ts, .rs bestanden."""
    extensions = {".py", ".ts", ".rs"}
    all_results = {}
    file_stats = []

    for root, dirs, files in os.walk(path):
        for f in sorted(files):
            ext = os.path.splitext(f)[1].lower()
            if ext not in extensions:
                continue
            filepath = os.path.join(root, f)
            try:
                results = analyze_file(filepath)
                if results:
                    rel_path = os.path.relpath(filepath, path)
                    all_results[rel_path] = results
                    avg_c = sum(r["cyclomatic_complexity"] for r in results) / len(results)
                    file_stats.append((rel_path, avg_c, len(results)))
            except Exception as e:
                print(f"Fout bij {filepath}: {e}", file=sys.stderr)

    if json_output:
        print(json.dumps(all_results, indent=2))
        return

    # Print per bestand
    for rel_path in sorted(all_results.keys()):
        results = all_results[rel_path]
        print(f"\n{'─' * 60}")
        print(f"  Bestand: {rel_path}")
        print(f"{'─' * 60}")
        print_table(results, threshold)

        summ = summary(results)
        print_summary(summ, rel_path)

    # Algemene samenvatting
    if file_stats:
        file_stats_sorted = sorted(file_stats, key=lambda x: x[1], reverse=True)
        print(f"\n{'=' * 60}")
        print(f"  ALGEMENE SAMENVATTING ({len(file_stats)} bestanden)")
        print(f"{'=' * 60}")
        print(f"  Bestanden met hoogste gemiddelde complexiteit:")
        print(f"  {'-' * 50}")
        for rel_path, avg_c, n_funcs in file_stats_sorted[:5]:
            print(f"  {rel_path:<40} avg cyclo={avg_c:<6.2f}  ({n_funcs} functies)")


def main():
    """main."""
    parser = argparse.ArgumentParser(
        description="Complexity meter — cyclomatische complexiteit & cognitieve load",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Voorbeelden:\n"
            "  python complexity.py bestand.py\n"
            "  python complexity.py src/ --recursive\n"
            "  python complexity.py src/ --recursive --json\n"
            "  python complexity.py src/ --recursive --threshold 10\n"
        ),
    )
    parser.add_argument("path", help="Bestand of directory om te analyseren")
    parser.add_argument("--recursive", "-r", action="store_true", help="Recursief scannen")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--threshold",
        "-t",
        type=int,
        default=0,
        help="Alleen functies rapporteren met complexiteit > N",
    )

    args = parser.parse_args()

    path = args.path

    if not os.path.exists(path):
        print(f"Fout: pad '{path}' bestaat niet.", file=sys.stderr)
        sys.exit(1)

    if args.recursive:
        if os.path.isfile(path):
            print(
                f"Fout: --recursive werkt alleen met directories, niet met bestanden.",
                file=sys.stderr,
            )
            sys.exit(1)
        scan_recursive(path, args.threshold, args.json)
        return

    if os.path.isdir(path):
        print(
            f"Fout: '{path}' is een directory. Gebruik --recursive om te scannen.", file=sys.stderr
        )
        sys.exit(1)

    results = analyze_file(path)

    if args.json:
        print(json.dumps(summary(results), indent=2))
        return

    print(f"\n{'─' * 60}")
    print(f"  Analyse: {path}")
    print(f"{'─' * 60}")
    print_table(results, args.threshold)

    summ = summary(results)
    print_summary(summ, path)


if __name__ == "__main__":
    main()
