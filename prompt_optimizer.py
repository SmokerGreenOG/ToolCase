#!/usr/bin/env python3
"""
prompt_optimizer.py — Analyseer en optimaliseer AI prompts in code.

Detecteert:
  - System prompts in Hermes/Claude/Codex configs
  - Prompt strings, templates, f-strings
  - Te lange/te korte prompts
  - Ontbrekende context, dubbelzinnigheid
  - Schat token count (GPT/Claude)
  - Geeft verbetersuggesties

Gebruik:
    python prompt_optimizer.py <file/dir>         # Analyseer prompts
    python prompt_optimizer.py <file/dir> --json   # JSON output
    python prompt_optimizer.py --analyze "prompt text"  # Directe prompt analyse

Categories:
    system_prompt:  System prompt (>50 tokens)
    user_prompt:    User/task prompt
    template:       Jinja2/f-string template met prompt
    unknown:        Kon niet geclassificeerd worden

Metrics per prompt:
    - Token count (4-char rule, ~0.75 words/token)
    - Readability (Flesch-style: lengte + complexiteit)
    - Clarity: heeft het voorbeelden? Output format? Constraints?
"""

from __future__ import annotations

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import ast
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

# ── ReST style prompts patterns ──────────────────────
PROMPT_PATTERNS = {
    "system_prompt": re.compile(
        r'(?i)(?:system|SYSTEM)_(?:prompt|MESSAGE|instruction)\s*[=:]\s*["\']',
    ),
    "user_prompt": re.compile(
        r'(?i)(?:user|HUMAN|task)_(?:prompt|message|input)\s*[=:]\s*["\']',
    ),
    "prompt_template": re.compile(
        r'(?i)(?:prompt|instruction|template)\s*=\s*(?:f|fr|rf)?["\']',
    ),
    "hermes_prompt": re.compile(
        r'(?i)(?:role|content)\s*[=:]\s*["\'](?:system|user|assistant)',
    ),
    "claude_prompt": re.compile(
        r'(?i)(?:text|content)\s*[=:]\s*["\'].{10,}(?:system|instruction|task)',
    ),
}

EXCLUDE_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".backups",
        ".self_improve_reports",
        "release",
        "build",
        "dist",
        ".rsi_backups",
        ".rsi_reports",
    }
)

LONG_PROMPT_THRESHOLD = 2000  # chars
SHORT_PROMPT_THRESHOLD = 30  # chars


# ── Data classes ──────────────────────────────────────


class PromptFinding:
    """A single prompt finding."""

    __slots__ = (
        "file",
        "line",
        "prompt_text",
        "category",
        "token_estimate",
        "clarity_score",
        "issues",
        "suggestions",
        "severity",
    )

    def __init__(
        self, file: str = "", line: int = 0, prompt_text: str = "", category: str = "unknown"
    ):
        self.file = file
        self.line = line
        self.prompt_text = prompt_text[:500]
        self.category = category
        self.token_estimate = 0
        self.clarity_score = 1.0
        self.issues: list[str] = []
        self.suggestions: list[str] = []
        self.severity = "info"

    def to_dict(self) -> dict:
        """to dict."""
        return {
            "file": self.file,
            "line": self.line,
            "prompt_text": self.prompt_text[:200],
            "category": self.category,
            "token_estimate": self.token_estimate,
            "clarity_score": round(self.clarity_score, 2),
            "issues": self.issues,
            "suggestions": self.suggestions,
            "severity": self.severity,
        }


# ── Core analysis functions ──────────────────────────


def estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars per token average)."""
    return max(1, math.ceil(len(text) / 4))


def analyze_prompt_text(prompt: str, finding: PromptFinding) -> PromptFinding:
    """Analyze a single prompt string for quality issues."""
    finding.prompt_text = prompt.strip()
    finding.token_estimate = estimate_tokens(finding.prompt_text)

    # ── Length checks ──
    if len(prompt) > LONG_PROMPT_THRESHOLD:
        finding.issues.append(
            f"Lange prompt ({len(prompt)} chars, ~{finding.token_estimate} tokens)"
        )
        finding.suggestions.append("Overweeg de prompt op te splitsen in kleinere delen")
        finding.severity = "medium"

    elif len(prompt) < SHORT_PROMPT_THRESHOLD and len(prompt) > 5:
        finding.issues.append(f"Korte prompt ({len(prompt)} chars) — mogelijk te weinig context")
        finding.suggestions.append("Voeg voorbeelden, output format, of constraints toe")
        finding.severity = "low"

    # ── Clarity checks ──
    clarity_checks = 0
    clarity_passed = 0

    # Check voor output format
    clarity_checks += 1
    if any(
        kw in prompt.lower() for kw in ("output", "format", "json", "markdown", "return ", "print ")
    ):
        clarity_passed += 1
    else:
        finding.issues.append("Geen output format gespecificeerd")
        finding.suggestions.append(
            "Specificeer output format: 'Geef antwoord als JSON' of 'Gebruik Markdown'"
        )

    # Check voor voorbeelden (few-shot)
    clarity_checks += 1
    has_example = any(
        kw in prompt.lower()
        for kw in (
            "bijvoorbeeld",
            "example",
            "e.g.",
            "i.e.",
            "zoals",
            "for instance",
            ":\n- ",
            ":\n  ",
        )
    )
    if has_example:
        clarity_passed += 1
    else:
        finding.issues.append("Geen voorbeelden (few-shot) in prompt")
        finding.suggestions.append("Voeg 1-3 voorbeelden toe: 'Bijvoorbeeld: [...]'")

    # Check voor constraints
    clarity_checks += 1
    if any(
        kw in prompt.lower()
        for kw in (
            "niet",
            "geen",
            "no",
            "don't",
            "vermeid",
            "avoid",
            "max",
            "limit",
            "min",
            "moet",
            "must",
            "should",
        )
    ):
        clarity_passed += 1
    else:
        finding.issues.append("Geen constraints/limieten gedefinieerd")
        finding.suggestions.append("Voeg constraints toe: 'Max 100 woorden', 'Niet hallucineren'")

    # Check voor chain-of-thought
    clarity_checks += 1
    if any(
        kw in prompt.lower()
        for kw in ("stap", "step", "eerst", "first", "dan", "then", "think", "reason", "overweeg")
    ):
        clarity_passed += 1
    else:
        finding.issues.append("Geen chain-of-thought instructie")
        finding.suggestions.append("Voeg redeneerstappen toe: 'Denk stap voor stap na'")

    # Check voor person/role
    clarity_checks += 1
    if any(
        kw in prompt.lower()
        for kw in (
            "je bent",
            "you are",
            "act as",
            "role",
            "expert",
            "assistent",
            "assistant",
            "specialist",
        )
    ):
        clarity_passed += 1
    else:
        finding.issues.append("Geen role/persona gedefinieerd")
        finding.suggestions.append("Geef de AI een rol: 'Je bent een ervaren Python developer'")

    if clarity_checks > 0:
        finding.clarity_score = clarity_passed / clarity_checks

    # ── Severity based on issues count ──
    if finding.severity == "info":
        if len(finding.issues) >= 4:
            finding.severity = "high"
        elif len(finding.issues) >= 2:
            finding.severity = "medium"
        elif finding.issues:
            finding.severity = "low"

    return finding


def extract_prompts_from_python(filepath: Path) -> list[PromptFinding]:
    """Extract prompt strings from a Python file using AST."""
    findings = []
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return findings

    for node in ast.walk(tree):
        # String constants that look like prompts
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value.strip()
            if len(text) > 20 and any(
                kw in text.lower()
                for kw in (
                    "prompt",
                    "instruction",
                    "system",
                    "assistant",
                    "je bent",
                    "you are",
                    "act as",
                    "task:",
                    "goal:",
                )
            ):
                finding = PromptFinding(
                    file=str(filepath),
                    line=getattr(node, "lineno", 0),
                    prompt_text=text,
                    category="system_prompt",
                )
                findings.append(analyze_prompt_text(text, finding))

        # f-strings with prompt content
        elif isinstance(node, ast.JoinedStr):
            text = _reconstruct_fstring(node)
            if len(text) > 30 and any(
                kw in text.lower()
                for kw in ("prompt", "instruction", "system", "act as", "je bent")
            ):
                finding = PromptFinding(
                    file=str(filepath),
                    line=getattr(node, "lineno", 0),
                    prompt_text=text[:500],
                    category="template",
                )
                findings.append(analyze_prompt_text(text, finding))

    return findings


def _reconstruct_fstring(node: ast.JoinedStr) -> str:
    """Reconstruct an f-string from AST nodes (approximate)."""
    parts = []
    for value in node.values:
        if isinstance(value, ast.Constant):
            parts.append(str(value.value))
        elif isinstance(value, ast.FormattedValue):
            parts.append("{...}")
    return "".join(parts)


def find_prompt_files(path: Path) -> list[Path]:
    """Find all Python files that may contain prompts."""
    files = []
    if path.is_file():
        if path.suffix == ".py":
            return [path]
        return []

    for root, dirs, filenames in os.walk(path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fn in filenames:
            fp = Path(root) / fn
            if fp.suffix == ".py":
                files.append(fp)
    return sorted(files)


# ── Analyzer class ──────────────────────────────────


class PromptOptimizer:
    """Main analyzer class."""

    def __init__(self, path: Path):
        self.path = path
        self.findings: list[PromptFinding] = []
        self.stats = {
            "files_scanned": 0,
            "prompts_found": 0,
            "total_tokens": 0,
            "avg_clarity": 0.0,
            "by_severity": {"high": 0, "medium": 0, "low": 0, "info": 0},
        }

    def run(self) -> list[PromptFinding]:
        """run."""
        files = find_prompt_files(self.path)
        self.stats["files_scanned"] = len(files)

        for fp in files:
            prompts = extract_prompts_from_python(fp)
            self.findings.extend(prompts)

        self.stats["prompts_found"] = len(self.findings)
        self.stats["total_tokens"] = sum(f.token_estimate for f in self.findings)

        if self.findings:
            self.stats["avg_clarity"] = sum(f.clarity_score for f in self.findings) / len(
                self.findings
            )

        for f in self.findings:
            self.stats["by_severity"][f.severity] = self.stats["by_severity"].get(f.severity, 0) + 1

        return self.findings

    def get_report(self) -> dict:
        """Get report."""
        return {
            "path": str(self.path),
            "stats": self.stats,
            "findings": [f.to_dict() for f in self.findings],
        }


# ── Display ──────────────────────────────────────────


def print_report(findings: list[PromptFinding], stats: dict) -> None:
    """Print a formatted report."""
    print()
    print("=" * 60)
    print(" 🧠  PROMPT OPTIMIZER — Analyse rapport")
    print("=" * 60)

    # Summary
    sev = stats["by_severity"]
    print()
    print(f"   📄 Files scanned:     {stats['files_scanned']}")
    print(f"   🧠 Prompts found:     {stats['prompts_found']}")
    print(f"   📊 Total tokens:      ~{stats['total_tokens']:,}")
    print(f"   🎯 Avg clarity:       {stats['avg_clarity']:.0%}")
    print(f"   🔴 High severity:     {sev.get('high', 0)}")
    print(f"   🟡 Medium severity:   {sev.get('medium', 0)}")
    print(f"   🟢 Low severity:      {sev.get('low', 0)}")
    print(f"   ℹ️  Info:              {sev.get('info', 0)}")

    if not findings:
        print()
        print("   ✨ Geen prompts gevonden. Code bevat geen AI prompt strings.")
        return

    # Per finding
    for i, f in enumerate(findings, 1):
        severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢", "info": "ℹ️"}
        icon = severity_icon.get(f.severity, "•")
        print()
        print(f" {icon}  #{i} — {f.file}:{f.line}  [{f.severity.upper()}]")
        print(
            f"     Category: {f.category}  |  Tokens: ~{f.token_estimate}  "
            f"|  Clarity: {f.clarity_score:.0%}"
        )
        print(f"     Preview:  {f.prompt_text[:120]}...")

        for issue in f.issues[:4]:
            print(f"     ⚠  {issue}")
        for suggestion in f.suggestions[:3]:
            print(f"     💡 {suggestion}")
        if len(f.issues) > 4:
            print(f"     ... en {len(f.issues) - 4} meer issues")

    # Score
    print()
    print("-" * 60)
    if stats["avg_clarity"] < 0.3:
        grade = "🔴 Laag — Prompts hebben veel verbetering nodig"
    elif stats["avg_clarity"] < 0.6:
        grade = "🟡 Matig — Enkele prompts kunnen beter"
    elif stats["avg_clarity"] < 0.8:
        grade = "🟢 Goed — Meerderheid van prompts is duidelijk"
    else:
        grade = "✅ Uitstekend — Prompts zijn goed geschreven"
    print(f"   Grade: {grade}")
    print()


def analyze_direct_prompt(prompt: str) -> dict:
    """Analyze a direct prompt string (--analyze flag)."""
    finding = PromptFinding(file="<direct>", line=0, prompt_text=prompt)
    finding = analyze_prompt_text(prompt, finding)
    return finding.to_dict()


# ── Main CLI ──────────────────────────────────────────


def main() -> None:
    """main."""
    parser = argparse.ArgumentParser(
        description="🧠 Prompt Optimizer — Analyseer en optimaliseer AI prompts in code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python prompt_optimizer.py .                    # Scan hele project
  python prompt_optimizer.py improve.py            # Enkel bestand
  python prompt_optimizer.py . --json              # JSON output
  python prompt_optimizer.py --analyze "Help me"   # Directe prompt analyse
  python prompt_optimizer.py --min-tokens 10       # Minimum prompt tokens
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Bestand of directory om te scannen")
    parser.add_argument(
        "--analyze", "-a", metavar="PROMPT", help="Analyseer een directe prompt string"
    )
    parser.add_argument("--json", "-j", action="store_true", help="Output als JSON")
    parser.add_argument(
        "--min-tokens", type=int, default=5, help="Minimum tokens voor prompt detectie (default: 5)"
    )
    parser.add_argument("--version", action="version", version="prompt_optimizer.py v1.0.0")

    args = parser.parse_args()

    # Direct prompt analysis
    if args.analyze:
        result = analyze_direct_prompt(args.analyze)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print()
            print("=" * 60)
            print(" 🧠  PROMPT OPTIMIZER — Directe analyse")
            print("=" * 60)
            print(f"   📝 Prompt: {result['prompt_text'][:200]}")
            print(f"   🏷️  Category: {result['category']}")
            print(f"   📊 Tokens: ~{result['token_estimate']}")
            print(f"   🎯 Clarity: {result['clarity_score']:.0%}")
            print(f"   ⚠️  Severity: {result['severity']}")
            for issue in result.get("issues", []):
                print(f"     ⚠  {issue}")
            for sug in result.get("suggestions", []):
                print(f"     💡 {sug}")
            print()
        return

    # File/directory scan
    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    optimizer = PromptOptimizer(target)
    findings = optimizer.run()
    report = optimizer.get_report()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(findings, report["stats"])


if __name__ == "__main__":
    main()
