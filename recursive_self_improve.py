#!/usr/bin/env python3
from __future__ import annotations
"""
recursive_self_improve.py — Recursive Self-Improvement System (RSI).

Maakt ToolCase slimmer door zichzelf recursief te verbeteren:

Cyclus:
  Analyse -> Reflect -> Generate -> Evaluate -> Learn -> Repeat

  1. ANALYSE:  Meet codekwaliteit over alle tools (syntax, lint, types, tests, docs)
  2. REFLECT:  Bepaalt welke verbeteringen de meeste impact hebben (o.b.v. memory)
  3. GENERATE: Past verbeteringen toe met backup/preview/rollback
  4. EVALUATE: Test of verbeteringen werken (compile, tests, metrics)
  5. LEARN:    Slaat op wat werkte -> past criteria aan voor volgende cyclus
  6. REPEAT:   Start opnieuw met verbeterde state -- elke cyclus slimmer

Memory: .rsi_memory.json onthoudt wat werkte, wat niet, en geleerde patronen.

Gebruik:
    python recursive_self_improve.py                           # 1 cycle (default)
    python recursive_self_improve.py --cycles 5                # 5 recursieve cycli
    python recursive_self_improve.py --focus types             # Focus op type hints
    python recursive_self_improve.py --learn-from memory.json  # Laad eerdere memory
    python recursive_self_improve.py --dry-run                 # Alleen analyse
    python recursive_self_improve.py --json                    # Machine-readable

Focus modes:
    all          -- Alle categorieen (default)
    types        -- Type hints toevoegen/verbeteren
    docs         -- Docstrings en documentatie
    code-quality -- Lint, complexity, naming
    tests        -- Test coverage verbeteren
    security     -- Security patterns verbeteren
"""
__maker__ = "SmokerGreenOG"

import _protect
import argparse
import ast
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# -- Constants
TOOLCASE_DIR = Path(__file__).parent.resolve()
MEMORY_FILE = TOOLCASE_DIR / ".rsi_memory.json"
REPORT_DIR = TOOLCASE_DIR / ".rsi_reports"
BACKUP_DIR = TOOLCASE_DIR / ".rsi_backups"
MAX_CYCLES = 10
TIMEOUT_SHORT = 15
TIMEOUT_MEDIUM = 60

DEFAULT_WEIGHTS = {
    "syntax_errors": 10.0,
    "type_coverage": 3.0,
    "docstring_coverage": 2.0,
    "e501_long_lines": 3.5,
    "e302_blank_lines": 1.5,
    "test_coverage": 4.0,
    "complexity": 2.5,
    "dead_code": 5.0,
    "security_issues": 8.0,
    "todo_markers": 1.5,
}

EXCLUDE_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".backups", ".self_improve_reports", "release", "build", "dist",
    ".rsi_reports", ".rsi_backups",
})


def _c(text: str, code: str = "") -> str:
    codes = {"green": "32", "yellow": "33", "red": "31",
             "cyan": "36", "magenta": "35", "bold": "1", "dim": "2"}
    c_code = codes.get(code, "")
    return f"\033[{c_code}m{text}\033[0m" if c_code else text


# === DATA CLASSES ===

@dataclass


class MetricSnapshot:
    file: str = ""
    syntax_ok: bool = True
    lines: int = 0
    e501_count: int = 0
    e302_count: int = 0
    type_hints: int = 0
    functions_total: int = 0
    functions_typed: int = 0
    docstrings: int = 0
    complexity_score: float = 0.0
    todos: int = 0
    dead_imports: int = 0
    security_issues: int = 0
    def quality_score(self) -> float:
        """Overall quality 0.0-1.0. Strings-docstrings excluded from E501."""
        issues = 0.0
        if not self.syntax_ok:
            issues += 100
        issues += self.e501_count * 0.5
        issues += self.e302_count * 0.3
        issues += self.todos * 1.0
        issues += self.dead_imports * 3.0
        issues += self.security_issues * 5.0
        denom = issues + 50.0
        return max(0.0, 1.0 - (issues / denom)) if denom > 0 else 1.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass


class ImprovementAttempt:
    cycle: int = 0
    category: str = ""
    file: str = ""
    description: str = ""
    old_hash: str = ""
    new_hash: str = ""
    success: bool = False
    metric_before: float = 0.0
    metric_after: float = 0.0
    duration_ms: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass


class LearnedPattern:
    pattern_id: str = ""
    category: str = ""
    description: str = ""
    times_tried: int = 0
    times_success: int = 0
    avg_improvement: float = 0.0
    last_used_cycle: int = 0
    code: str = ""

    @property
    def success_rate(self) -> float:
        return self.times_success / max(1, self.times_tried)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass


class CycleReport:
    cycle: int = 0
    focus: str = "all"
    duration_s: float = 0.0
    files_analyzed: int = 0
    total_quality_before: float = 0.0
    total_quality_after: float = 0.0
    improvements_attempted: int = 0
    improvements_succeeded: int = 0
    improvements_failed: int = 0
    patterns_used: int = 0
    patterns_learned: int = 0
    metrics: list[MetricSnapshot] = field(default_factory=list)
    attempts: list[ImprovementAttempt] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = "running"

    def to_dict(self) -> dict:
        return {
            "cycle": self.cycle,
            "focus": self.focus,
            "duration_s": round(self.duration_s, 2),
            "files_analyzed": self.files_analyzed,
            "quality_before": round(self.total_quality_before, 3),
            "quality_after": round(self.total_quality_after, 3),
            "improvement": round(self.total_quality_after - self.total_quality_before, 3),
            "attempted": self.improvements_attempted,
            "succeeded": self.improvements_succeeded,
            "failed": self.improvements_failed,
            "patterns_used": self.patterns_used,
            "patterns_learned": self.patterns_learned,
            "status": self.status,
            "errors": self.errors[:5],
        }


# === IMPROVEMENT MEMORY ===


class ImprovementMemory:
    """Leert van elke cyclus en wordt slimmer."""

    def __init__(self, path: Path = MEMORY_FILE):
        self.path = path
        self.weights: dict[str, float] = dict(DEFAULT_WEIGHTS)
        self.patterns: list[LearnedPattern] = []
        self.history: list[ImprovementAttempt] = []
        self.total_cycles = 0
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.weights.update(data.get("weights", {}))
                self.patterns = [LearnedPattern(**p) for p in data.get("patterns", [])]
                self.history = [ImprovementAttempt(**a) for a in data.get("history", [])]
                self.total_cycles = data.get("total_cycles", 0)
            except (json.JSONDecodeError, TypeError):
                pass

    def save(self) -> None:
        data = {
            "weights": self.weights,
            "patterns": [p.to_dict() for p in self.patterns],
            "history": [a.to_dict() for a in self.history[-100:]],
            "total_cycles": self.total_cycles,
            "last_updated": datetime.now().isoformat(),
        }
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def record_attempt(self, attempt: ImprovementAttempt) -> None:
        self.history.append(attempt)
        for pattern in self.patterns:
            if pattern.category == attempt.category and pattern.pattern_id in attempt.description:
                pattern.times_tried += 1
                if attempt.success:
                    pattern.times_success += 1
                improvement = attempt.metric_after - attempt.metric_before
                pattern.avg_improvement = (
                    (pattern.avg_improvement * (pattern.times_tried - 1) + improvement)
                    / pattern.times_tried
                )
                pattern.last_used_cycle = self.total_cycles
                break
        if attempt.success and attempt.metric_after > attempt.metric_before:
            cat_key = self._cat_to_weight(attempt.category)
            if cat_key in self.weights:
                self.weights[cat_key] *= 1.05
        self.total_cycles += 1
        self.save()

    def learn_pattern(self, category: str, description: str, code: str = "") -> str:
        pid = hashlib.md5(f"{category}:{description}".encode()).hexdigest()[:12]
        for p in self.patterns:
            if p.pattern_id == pid:
                p.times_tried += 1
                return pid
        pattern = LearnedPattern(pattern_id=pid, category=category,
                                  description=description, times_tried=1,
                                  last_used_cycle=self.total_cycles, code=code)
        self.patterns.append(pattern)
        self.save()
        return pid

    def get_best_patterns(self, category: str, top_n: int = 3) -> list[LearnedPattern]:
        candidates = [p for p in self.patterns
                      if p.category == category and p.times_tried >= 2]
        candidates.sort(key=lambda p: p.success_rate * p.avg_improvement, reverse=True)
        return candidates[:top_n]

    def get_priority_categories(self) -> list[tuple[str, float]]:
        impact: dict[str, float] = {}
        for key, weight in self.weights.items():
            cat_attempts = [a for a in self.history if self._weight_to_cat(key) in a.category]
            sr = sum(1 for a in cat_attempts if a.success) / max(1, len(cat_attempts))
            impact[key] = weight * (1.0 + sr)
        return sorted(impact.items(), key=lambda x: x[1], reverse=True)

    @staticmethod
    def _cat_to_weight(category: str) -> str:
        mapping = {"syntax": "syntax_errors", "types": "type_coverage",
                   "docs": "docstring_coverage", "code-quality": "e501_long_lines",
                   "tests": "test_coverage", "complexity": "complexity",
                   "dead-code": "dead_code", "security": "security_issues",
                   "todos": "todo_markers"}
        for k, v in mapping.items():
            if k in category:
                return v
        return "code-quality"

    @staticmethod
    def _weight_to_cat(key: str) -> str:
        rev = {"syntax_errors": "syntax", "type_coverage": "types",
               "docstring_coverage": "docs", "e501_long_lines": "code-quality",
               "e302_blank_lines": "code-quality", "test_coverage": "tests",
               "complexity": "complexity", "dead_code": "dead-code",
               "security_issues": "security", "todo_markers": "todos"}
        return rev.get(key, "code-quality")


# === SELF ANALYZER ===


class SelfAnalyzer:
    """Meet eigen codekwaliteit."""

    def __init__(self, workspace: Path, focus: str = "all"):
        self.workspace = workspace
        self.focus = focus
        self.metrics: list[MetricSnapshot] = []

    def find_py_files(self) -> list[Path]:
        files = []
        seen = set()
        for root, dirs, filenames in os.walk(self.workspace):
            dirs[:] = [d for d in dirs
                       if d not in EXCLUDE_DIRS and not d.startswith(".")
                       and d != "__pycache__"]
            for fn in filenames:
                if fn.endswith(".py"):
                    fp = Path(root) / fn
                    if str(fp) not in seen:
                        seen.add(str(fp))
                        files.append(fp)
        return sorted(files)

    def analyze_file(self, filepath: Path) -> MetricSnapshot:
        m = MetricSnapshot(file=str(filepath))
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
            m.lines = len(content.splitlines())
            tree = ast.parse(content)
            m.syntax_ok = True
        except SyntaxError:
            m.syntax_ok = False
            return m
        except Exception:
            return m

        # Build set of lines that are inside string literals
        string_lines: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                    for ln in range(node.lineno, node.end_lineno + 1):
                        string_lines.add(ln)
            elif isinstance(node, ast.JoinedStr):
                if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                    for ln in range(node.lineno, node.end_lineno + 1):
                        string_lines.add(ln)

        for i, line in enumerate(content.splitlines()):
            if len(line) > 100 and (i + 1) not in string_lines:
                m.e501_count += 1

        lines = content.splitlines()
        for i, line in enumerate(lines):
            if i > 1 and line.startswith(("def ", "class ")):
                if lines[i - 1].strip() != "" or lines[i - 2].strip() != "":
                    m.e302_count += 1

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                m.functions_total += 1
                for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
                    if arg.annotation:
                        m.type_hints += 1
                if node.returns:
                    m.type_hints += 1
                if (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    m.docstrings += 1
                branches = sum(1 for n in ast.walk(node)
                               if isinstance(n, (ast.If, ast.While, ast.For,
                                                 ast.ExceptHandler, ast.With,
                                                 ast.AsyncFor, ast.AsyncWith)))
                m.complexity_score += branches

        # Count marker comments only (skip regex patterns in strings)
        m.todos = 0
        for i, line in enumerate(content.splitlines()):
            stripped = line.strip()
            if stripped.startswith("#") and re.search(r'(?:TODO|FIXME|HACK|BUG|XXX)', stripped):
                m.todos += 1
        return m

    def scan_all(self) -> list[MetricSnapshot]:
        self.metrics = []
        for fp in self.find_py_files():
            self.metrics.append(self.analyze_file(fp))
        return self.metrics

    def total_quality(self) -> float:
        if not self.metrics:
            return 0.0
        return sum(m.quality_score() for m in self.metrics) / len(self.metrics)

    def summary_stats(self) -> dict:
        total = len(self.metrics)
        if total == 0:
            return {}
        return {
            "files": total,
            "lines": sum(m.lines for m in self.metrics),
            "syntax_errors": sum(0 if m.syntax_ok else 1 for m in self.metrics),
            "e501_total": sum(m.e501_count for m in self.metrics),
            "e302_total": sum(m.e302_count for m in self.metrics),
            "functions_total": sum(m.functions_total for m in self.metrics),
            "quality_score": round(self.total_quality(), 3),
        }


# === IMPROVEMENT PLANNER ===


class ImprovementPlanner:
    def __init__(self, memory: ImprovementMemory, focus: str = "all"):
        self.memory = memory
        self.focus = focus

    def plan(self, metrics: list[MetricSnapshot], cycle: int) -> list[ImprovementAttempt]:
        attempts: list[ImprovementAttempt] = []
        seen = set()

        def add(a: ImprovementAttempt) -> None:
            key = f"{a.category}:{a.file}:{a.description[:60]}"
            if key not in seen:
                seen.add(key)
                attempts.append(a)

        if self.focus in ("all", "code-quality"):
            for m in metrics:
                if m.e501_count > 5:
                    add(ImprovementAttempt(cycle=cycle, category="code-quality",
                        file=m.file,
                        description=f"E501: {m.e501_count} lange regels in {Path(m.file).name}",
                        metric_before=m.quality_score()))
                if m.e302_count > 3:
                    add(ImprovementAttempt(cycle=cycle, category="code-quality",
                        file=m.file,
                        description=f"E302: {m.e302_count} ontbrekende blank lines",
                        metric_before=m.quality_score()))

        if self.focus in ("all", "types"):
            for m in metrics:
                if m.functions_total > 0 and m.type_hints == 0:
                    add(ImprovementAttempt(cycle=cycle, category="types",
                        file=m.file,
                        description=f"Types: 0 hints in {Path(m.file).name}",
                        metric_before=m.quality_score()))

        if self.focus in ("all", "docs"):
            for m in metrics:
                if m.functions_total > 0 and m.docstrings == 0:
                    add(ImprovementAttempt(cycle=cycle, category="docs",
                        file=m.file,
                        description=f"Docs: 0 docstrings in {Path(m.file).name}",
                        metric_before=m.quality_score()))

        if self.focus in ("all", "todos"):
            for m in metrics:
                if m.todos > 3:
                    add(ImprovementAttempt(cycle=cycle, category="todos",
                        file=m.file,
                        description=f"TODOs: {m.todos} markers in {Path(m.file).name}",
                        metric_before=m.quality_score()))

        priority_cats = self.memory.get_priority_categories()
        cat_order = {cat: i for i, (cat, _) in enumerate(priority_cats)}

        def sort_key(a: ImprovementAttempt) -> tuple:
            return (-cat_order.get(self.memory._cat_to_weight(a.category), 50),
                    -(a.metric_before or 0))

        attempts.sort(key=sort_key)
        return attempts[:20]


# === IMPROVEMENT EXECUTOR ===


class ImprovementExecutor:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.backups: dict[str, str] = {}

    def create_backup(self, filepath: Path) -> Optional[str]:
        if not filepath.exists():
            return None
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        bak_name = f"{filepath.name}.{ts}.rsi_bak"
        bak_path = BACKUP_DIR / bak_name
        shutil.copy2(str(filepath), str(bak_path))
        self.backups[str(filepath)] = str(bak_path)
        return str(bak_path)

    def rollback(self, filepath: Path) -> bool:
        key = str(filepath)
        if key in self.backups:
            bak = Path(self.backups[key])
            if bak.exists():
                shutil.copy2(str(bak), str(filepath))
                return True
        return False

    def apply_e501_fix(self, filepath: Path) -> tuple[bool, str]:
        """Fix long lines safely using AST to avoid breaking strings."""
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
            original = content
            lines = content.splitlines()

            # Use AST to find string literal line ranges
            string_lines: set[int] = set()
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                            for ln in range(node.lineno, node.end_lineno + 1):
                                string_lines.add(ln)
                    elif isinstance(node, ast.JoinedStr):  # f-strings
                        if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                            for ln in range(node.lineno, node.end_lineno + 1):
                                string_lines.add(ln)
            except SyntaxError:
                pass  # Can't parse, skip AST-based filtering

            new_lines = []
            fixed = 0
            for i, line in enumerate(lines):
                line_no = i + 1
                stripped = line.rstrip()
                if len(stripped) <= 100 or line_no in string_lines:
                    new_lines.append(line)
                    continue

                # Try to find a safe break point (after comma or operator)
                best_break = -1
                for bp in [90, 80, 70]:
                    idx = stripped.rfind(", ", 0, bp)
                    if idx > 20:
                        best_break = idx + 1  # After the comma
                        break
                if best_break < 0:
                    idx = stripped.rfind(" ", 70, 90)
                    if idx > 20:
                        best_break = idx

                if best_break > 20:
                    indent = len(line) - len(line.lstrip())
                    prefix_sp = " " * indent
                    new_lines.append(stripped[:best_break].rstrip())
                    new_lines.append(prefix_sp + stripped[best_break:].strip())
                    fixed += 1
                else:
                    new_lines.append(line)

            new_content = "\n".join(new_lines)
            if not new_content.endswith("\n"):
                new_content += "\n"
            if new_content != original and fixed > 0:
                # Verify it still compiles
                try:
                    ast.parse(new_content)
                except SyntaxError:
                    return False, "Syntax error na fix — teruggedraaid"
                filepath.write_text(new_content, encoding="utf-8")
                return True, f"E501: {fixed} lange regels gewrapped"
            return False, "Geen E501 fixes nodig"
        except Exception as e:
            return False, str(e)

    def apply_e302_fix(self, filepath: Path) -> tuple[bool, str]:
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
            original = content
            lines = content.splitlines()
            new_lines = list(lines)
            fixed = 0
            insertions = 0
            for i, line in enumerate(lines):
                if line.startswith(("def ", "class ", "async def ")):
                    if i >= 2:
                        blanks = 0
                        j = i - 1
                        while j >= 0 and lines[j].strip() == "":
                            blanks += 1
                            j -= 1
                        needed = 2 - blanks
                        for _ in range(needed):
                            new_lines.insert(i + insertions, "")
                            insertions += 1
                            fixed += 1
            new_content = "\n".join(new_lines)
            if new_content != original and fixed > 0:
                filepath.write_text(new_content, encoding="utf-8")
                return True, f"E302: {fixed} blank lines toegevoegd"
            return False, "Geen E302 fixes nodig"
        except Exception as e:
            return False, str(e)


# === EVALUATOR ===


class Evaluator:
    def __init__(self, workspace: Path):
        self.workspace = workspace

    def compile_check(self) -> tuple[bool, list[str]]:
        errors = []
        for pyfile in sorted(self.workspace.rglob("*.py")):
            if any(p.startswith(".") or p == "__pycache__"
                   for p in pyfile.parts):
                continue
            try:
                ast.parse(pyfile.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError as e:
                errors.append(f"{pyfile.name}: {e}")
        return len(errors) == 0, errors

    def test_check(self) -> tuple[bool, list[str]]:
        test_dir = self.workspace / "tests"
        if not test_dir.exists():
            return True, ["Geen tests/ directory"]
        try:
            r = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", str(test_dir)],
                capture_output=True, text=True, timeout=60,
            )
            ok = r.returncode == 0
            details = [l for l in (r.stdout + r.stderr).splitlines()
                       if l.strip() and ("FAIL" in l or "ERROR" in l or "OK" in l)]
            return ok, details or (["Alles OK"] if ok else ["Tests faalden"])
        except subprocess.TimeoutExpired:
            return False, ["Test timeout (60s)"]
        except Exception as e:
            return False, [str(e)]

    def evaluate(self) -> dict:
        compile_ok, compile_errs = self.compile_check()
        test_ok, test_details = self.test_check()
        return {
            "compile_ok": compile_ok,
            "compile_errors": compile_errs,
            "test_ok": test_ok,
            "test_details": test_details,
            "passed": compile_ok and test_ok,
        }


# === RECURSIVE LOOP ===


class RecursiveSelfImprove:
    """Main RSI loop -- elke cyclus wordt slimmer."""

    def __init__(self, workspace: Path, focus: str = "all",
                 dry_run: bool = False, memory_path: Optional[Path] = None):
        self.workspace = workspace
        self.focus = focus
        self.dry_run = dry_run
        self.memory = ImprovementMemory(memory_path or MEMORY_FILE)
        self.analyzer = SelfAnalyzer(workspace, focus)
        self.planner = ImprovementPlanner(self.memory, focus)
        self.executor = ImprovementExecutor(workspace)
        self.evaluator = Evaluator(workspace)
        self.reports: list[CycleReport] = []
        self.evolution_log: list[str] = []

    def run_cycle(self, cycle: int) -> CycleReport:
        print()
        print(_c(f"  {'='*56}", "cyan"))
        print(_c(f"  RSI Cycle {cycle} -- Focus: {self.focus.upper()}", "cyan"))
        if not self.dry_run:
            print(_c(f"     Memory: {len(self.memory.patterns)} patterns, "
                    f"{len(self.memory.history)} attempts", "dim"))
        print(_c(f"  {'='*56}", "cyan"))

        start_time = time.time()
        report = CycleReport(cycle=cycle, focus=self.focus)

        # STEP 1: ANALYSE
        print(_c(f"\n  1. ANALYSE -- Meten van codekwaliteit...", "bold"))
        metrics = self.analyzer.scan_all()
        report.metrics = metrics
        report.files_analyzed = len(metrics)
        report.total_quality_before = self.analyzer.total_quality()
        stats = self.analyzer.summary_stats()

        print(f"     Files: {stats.get('files',0)}  |  Lines: {stats.get('lines',0)}  |  "
              f"E501: {stats.get('e501_total',0)}")
        print(f"     Syntax OK: {stats.get('syntax_errors',0) == 0}  |  "
              f"Functions: {stats.get('functions_total',0)}")
        print(f"     Quality: {stats.get('quality_score', 0):.4f}")

        # STEP 2: REFLECT
        print(_c(f"\n  2. REFLECT -- Bepalen van prioriteiten...", "bold"))
        priorities = self.memory.get_priority_categories()[:5]
        if priorities:
            top_impact = max(1, priorities[0][1])
            print(f"     {len(priorities)} prioriteiten (geleerd uit {self.memory.total_cycles} cycli):")
            for cat, impact in priorities:
                bar_len = int(impact / top_impact * 10)
                bar = "#" * bar_len + "." * (10 - bar_len)
                print(f"       [{bar}] {cat:<25s} {impact:.1f}")

        # STEP 3: GENERATE
        print(_c(f"\n  3. GENERATE -- Verbeteringen plannen...", "bold"))
        attempts = self.planner.plan(metrics, cycle)
        report.improvements_attempted = len(attempts)
        print(f"     {len(attempts)} verbeteringen gepland")

        if self.dry_run:
            for a in attempts[:6]:
                print(f"       - {a.description[:80]}")
            if len(attempts) > 6:
                print(f"       ... en {len(attempts) - 6} meer")
        else:
            for attempt in attempts:
                filepath = Path(attempt.file)
                if not filepath.exists():
                    continue
                bak = self.executor.create_backup(filepath)
                success = False
                result_msg = ""

                if "E501" in attempt.description:
                    success, result_msg = self.executor.apply_e501_fix(filepath)
                elif "E302" in attempt.description:
                    success, result_msg = self.executor.apply_e302_fix(filepath)
                elif "Types" in attempt.description:
                    success, result_msg = False, "Types: handmatige review nodig"
                elif "Docs" in attempt.description:
                    success, result_msg = False, "Docs: handmatige review nodig"
                elif "TODO" in attempt.description:
                    success, result_msg = False, "TODOs: handmatige review nodig"

                attempt.success = success
                if success:
                    report.improvements_succeeded += 1
                    print(f"       + {result_msg}")
                    self.memory.learn_pattern(attempt.category, attempt.description)
                else:
                    report.improvements_failed += 1
                    if result_msg:
                        print(f"       . {result_msg}")
                report.attempts.append(attempt)

        # STEP 4: EVALUATE
        print(_c(f"\n  4. EVALUATE -- Controleren van resultaten...", "bold"))
        if not self.dry_run and report.improvements_succeeded > 0:
            eval_result = self.evaluator.evaluate()
            if eval_result["passed"]:
                print(f"     + Compile: OK  |  Tests: OK")
            else:
                print(f"     ! Compile errors: {len(eval_result['compile_errors'])}")
                for e in eval_result["compile_errors"][:3]:
                    print(f"       ! {e}")
                print(_c(f"     Rollback van alle wijzigingen...", "yellow"))
                for attempt in report.attempts:
                    if attempt.success:
                        self.executor.rollback(Path(attempt.file))
                report.status = "rolled_back"
        else:
            print(f"     . Geen wijzigingen om te evalueren")
            report.status = "completed"

        # STEP 5: RE-MEASURE
        print(_c(f"\n  5. METEN -- Opnieuw meten van kwaliteit...", "bold"))
        metrics_after = self.analyzer.scan_all()
        report.total_quality_after = self.analyzer.total_quality()
        delta = report.total_quality_after - report.total_quality_before
        d_str = _c(f"+{delta:.4f}", "green") if delta > 0 else _c(f"{delta:.4f}", "red")
        print(f"     Kwaliteit: {report.total_quality_before:.4f} -> "
              f"{report.total_quality_after:.4f} ({d_str})")

        # STEP 6: LEARN
        print(_c(f"\n  6. LEARN -- Opslaan van geleerde lessen...", "bold"))
        learned = 0
        for attempt in report.attempts:
            if attempt.success:
                self.memory.record_attempt(attempt)
                learned += 1
        report.patterns_learned = learned
        report.patterns_used = len(self.memory.patterns)
        print(f"     {learned} pogingen opgeslagen, totaal {len(self.memory.patterns)} patronen")

        report.duration_s = round(time.time() - start_time, 1)
        self.evolution_log.append(
            f"Cycle {cycle}: {report.total_quality_before:.4f} -> "
            f"{report.total_quality_after:.4f} ({delta:+.4f}), "
            f"{report.improvements_succeeded}/{report.improvements_attempted} ok, "
            f"{report.duration_s}s"
        )
        report.status = report.status or "completed"
        self.reports.append(report)
        return report

    def run(self, cycles: int = 1) -> list[CycleReport]:
        mode = _c("DRY-RUN", "yellow") if self.dry_run else _c("APPLY", "green")
        print()
        print(_c(f"  {'='*54}", "magenta"))
        print(_c(f"  RECURSIVE SELF-IMPROVEMENT v1.0", "magenta"))
        print(_c(f"  Mode: {mode}  |  Cycles: {cycles}  |  Focus: {self.focus.upper()}", "magenta"))
        print(_c(f"  Workspace: {self.workspace}", "magenta"))
        print(_c(f"  Memory: {len(self.memory.patterns)} patterns, "
                f"{len(self.memory.history)} past attempts", "magenta"))
        print(_c(f"  {'='*54}", "magenta"))

        for cycle in range(1, cycles + 1):
            report = self.run_cycle(cycle)
            if report.status == "rolled_back":
                print(_c(f"\n  Rollback -- stoppen met verdere cycli", "yellow"))
                break

        # Final report
        print()
        print(_c(f"  {'='*54}", "magenta"))
        print(_c(f"  RECURSIVE SELF-IMPROVEMENT -- EINDRAPPORT", "magenta"))
        print(_c(f"  {'='*54}", "magenta"))

        if self.reports:
            first_q = self.reports[0].total_quality_before
            last_q = self.reports[-1].total_quality_after
            total_delta = last_q - first_q
            arrow = _c("+", "green") if total_delta > 0 else _c("-", "red")

            print(f"\n  {'Cycle':<7s} {'Voor':>10s} {'Na':>10s} {'Delta':>10s}  Status")
            print(f"  {'-'*45}")
            for r in self.reports:
                d = r.total_quality_after - r.total_quality_before
                ds = _c(f"{d:+.4f}", "green") if d > 0 else _c(f"{d:.4f}", "red")
                print(f"  #{r.cycle:<4d}  {r.total_quality_before:.4f}  "
                      f"{r.total_quality_after:.4f}  {ds}  {r.status.upper()}")

            print(f"\n  {arrow} Totaal over {len(self.reports)} cycli: "
                  f"{first_q:.4f} -> {last_q:.4f} ({total_delta:+.4f})")
            print(f"  Geleerde patronen: {len(self.memory.patterns)}")
            print(f"  Memory: {MEMORY_FILE}")

            REPORT_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            rf = REPORT_DIR / f"rsi_report_{ts}.json"
            rf.write_text(json.dumps([r.to_dict() for r in self.reports],
                                     indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  Report saved: {rf}")

        return self.reports

    def get_json_report(self) -> dict:
        return {
            "focus": self.focus,
            "dry_run": self.dry_run,
            "cycles_completed": len(self.reports),
            "memory_patterns": len(self.memory.patterns),
            "memory_attempts": len(self.memory.history),
            "reports": [r.to_dict() for r in self.reports],
            "evolution": self.evolution_log,
        }


# === MAIN CLI ===


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RSI -- Recursive Self-Improvement voor ToolCase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("path", nargs="?", default=".", help="ToolCase directory")
    parser.add_argument("--cycles", "-c", type=int, default=1,
                        help=f"Aantal cycli (max {MAX_CYCLES})")
    parser.add_argument("--focus", "-f",
                        choices=["all", "types", "docs", "code-quality", "todos"],
                        default="all", help="Focus area")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Alleen analyse")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--learn-from", metavar="FILE", help="Laad memory uit bestand")
    parser.add_argument("--version", action="version", version="rsi v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f"Bestand '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    cycles = min(args.cycles, MAX_CYCLES)
    memory_path = Path(args.learn_from).resolve() if args.learn_from else None

    rsi = RecursiveSelfImprove(
        workspace=target, focus=args.focus,
        dry_run=args.dry_run, memory_path=memory_path,
    )
    reports = rsi.run(cycles=cycles)

    if args.json:
        print(json.dumps(rsi.get_json_report(), indent=2, ensure_ascii=False))

    if reports:
        first_q = reports[0].total_quality_before
        last_q = reports[-1].total_quality_after
        if last_q > first_q:
            sys.exit(0)
        elif last_q == first_q:
            sys.exit(1)
        else:
            sys.exit(2)


if __name__ == "__main__":
    main()