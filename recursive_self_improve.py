#!/usr/bin/env python3
from __future__ import annotations
"""
recursive_self_improve.py — Recursive Self-Improvement System (RSI) v2.0.

Maakt ToolCase slimmer door zichzelf recursief te verbeteren.
Nieuw in v2.0: LLM Bridge integratie — Hermes wordt ingeschakeld voor
intelligente fixes (docs, types, refactors, security, tests).

Cyclus:
  Analyse -> Reflect -> Plan -> Fix (auto + LLM queue) -> Evaluate -> Learn -> Repeat

  1. ANALYSE:  Meet codekwaliteit over alle tools (syntax, lint, types, tests, docs)
  2. REFLECT:  Bepaalt welke verbeteringen de meeste impact hebben (o.b.v. memory)
  3. PLAN:     Genereert fix-plan — splitst in auto-fixable vs LLM-required
  4. FIX:      Auto-fixes direct toepassen; LLM fixes naar queue voor Hermes
  5. EVALUATE: Test of verbeteringen werken (compile, tests, metrics)
  6. LEARN:    Slaat op wat werkte -> past criteria aan voor volgende cyclus
  7. REPEAT:   Start opnieuw met verbeterde state -- elke cyclus slimmer

Focus modes (nieuw in v2.0):
    all            -- Alle categorieen (default)
    types          -- Type hints toevoegen/verbeteren
    docs           -- Docstrings en documentatie
    code-quality   -- Lint, complexity, naming
    tests          -- Test coverage + test generatie
    security       -- Security patterns verbeteren
    refactor       -- Code refactoring
    performance    -- Performance optimalisaties
    architecture   -- Cross-file structuur verbeteringen
    dead-code      -- Dead code opschonen

LLM Bridge modi:
    --auto-only    Alleen auto-fixes (E501, E302, etc.), geen LLM queue
    --llm-queue    Schrijf complexe fixes naar queue voor Hermes
    --llm-eval     Evalueer resultaten uit de LLM queue en leer ervan

Gebruik:
    python recursive_self_improve.py                           # 1 cycle (auto + queue)
    python recursive_self_improve.py --cycles 5                # 5 recursieve cycli
    python recursive_self_improve.py --focus docs              # Focus op docs
    python recursive_self_improve.py --llm-queue               # Alleen queue vullen
    python recursive_self_improve.py --llm-eval                # Queue resultaten evalueren
    python recursive_self_improve.py --dry-run                 # Alleen analyse
    python recursive_self_improve.py --json                    # Machine-readable
"""

__maker__ = "SmokerGreenOG"
__version__ = "2.0.0"

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

# ── Import LLM Bridge ──────────────────────────────────────────
try:
    from rsi_llm_bridge import LLMBridge, FixRequest, FixResult, LLM_FIXABLE, AUTO_FIXABLE
except ImportError:
    # Fallback: bridge niet beschikbaar — alle fixes in AUTO_FIXABLE modus
    LLMBridge = None
    FixRequest = None
    FixResult = None
    LLM_FIXABLE = frozenset()
    AUTO_FIXABLE = frozenset({"e501", "e302"})

# ── Constants ───────────────────────────────────────────────────

TOOLCASE_DIR = Path(__file__).parent.resolve()
MEMORY_FILE = TOOLCASE_DIR / ".rsi_memory.json"
MAX_CYCLES = 10
TIMEOUT_SHORT = 15
TIMEOUT_MEDIUM = 60

DEFAULT_WEIGHTS = {
    "syntax_errors": 10.0,
    "type_coverage": 3.0,
    "docstring_coverage": 3.5,    # Verhoogd in v2.0
    "e501_long_lines": 2.0,       # Verlaagd — minder impactvol
    "e302_blank_lines": 1.0,      # Verlaagd — cosmetisch
    "test_coverage": 5.0,         # Verhoogd in v2.0
    "complexity": 2.5,
    "dead_code": 5.0,
    "security_issues": 8.0,
    "todo_markers": 1.5,
    "cross_file_duplication": 4.0,  # Nieuw in v2.0
    "import_hygiene": 3.0,          # Nieuw in v2.0
    "error_handling": 4.0,          # Nieuw in v2.0
    "naming_conventions": 2.0,      # Nieuw in v2.0
}

EXCLUDE_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".backups", ".self_improve_reports", "release", "build", "dist",
    ".rsi_reports", ".rsi_backups", ".rsi_fix_queue",
})

# Mapping van focus -> issue types die de LLM kan fixen
FOCUS_TO_ISSUE_TYPES = {
    "all": LLM_FIXABLE,
    "types": {"types"},
    "docs": {"docs"},
    "code-quality": {"e501", "e302", "trailing_ws", "naming"},
    "tests": {"tests"},
    "security": {"security"},
    "refactor": {"refactor", "complexity", "naming"},
    "performance": {"performance", "complexity"},
    "architecture": {"refactor", "imports"},
    "dead-code": {"dead_code"},
    "bugs": {"bugfix", "error_handling"},
}


def _c(text: str, code: str = "") -> str:
    """ c.
    
        Args:
            text: Description.
            code: Description.
    
        Returns:
            Description.
        """
    codes = {"green": "32", "yellow": "33", "red": "31",
             "cyan": "36", "magenta": "35", "bold": "1", "dim": "2",
             "blue": "34", "white": "37"}
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
    # Nieuwe metrics v2.0
    error_handlers: int = 0      # try/except blocks
    naming_issues: int = 0        # Niet-Pythonic names
    import_count: int = 0         # Aantal imports
    test_functions: int = 0       # Aantal test functies

    def quality_score(self) -> float:
        """Overall quality 0.0-1.0. 1.0 = excellent, negligible issues."""
        penalty = 0.0
        if not self.syntax_ok:
            penalty += 20.0
        # Kleine issues: pas straffen bij substantiële aantallen
        if self.e501_count > 5:
            penalty += (self.e501_count - 5) * 0.1
        if self.e302_count > 5:
            penalty += (self.e302_count - 5) * 0.1
        if self.todos > 5:
            penalty += (self.todos - 5) * 0.5
        penalty += self.dead_imports * 2.0
        penalty += self.security_issues * 5.0
        # Docs: pas straffen bij >70% missend EN minimaal 3 missende
        if self.functions_total > 0:
            docs_missing_count = self.functions_total - self.docstrings
            docs_missing = docs_missing_count / self.functions_total
            if docs_missing > 0.70 and docs_missing_count >= 3:
                penalty += docs_missing * 5.0
            # Types: skip test files (test_*.py, *_test.py)
            fname = Path(self.file).name
            is_test = fname.startswith('test_') or fname.endswith('_test.py')
            if not is_test:
                types_missing = 1.0 - (self.type_hints / max(1, self.functions_total * 2))
                if types_missing > 0.85 and self.functions_total >= 5:
                    penalty += types_missing * 3.0
        penalty += self.naming_issues * 0.5
        # Score: 1.0 - penalty/100, floor 0.0, praktisch 1.0 bij penalty < 0.5
        raw = max(0.0, 1.0 - (penalty / 100.0))
        return 1.0 if raw > 0.995 else raw

    def to_dict(self) -> dict:
        """to dict.
            """
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
    fix_method: str = "auto"    # "auto" | "llm_bridge"
    bridge_request_id: str = "" # ID van de LLM bridge request

    def to_dict(self) -> dict:
        """to dict.
            """
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
    fix_method: str = "auto"    # "auto" | "llm_bridge"

    @property
    def success_rate(self) -> float:
        """success rate.
            """
        return self.times_success / max(1, self.times_tried)

    def to_dict(self) -> dict:
        """to dict.
            """
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
    improvements_queued: int = 0    # Nieuw: naar LLM queue
    patterns_used: int = 0
    patterns_learned: int = 0
    metrics: list[MetricSnapshot] = field(default_factory=list)
    attempts: list[ImprovementAttempt] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = "running"
    # Nieuwe v2.0 velden
    cross_file_issues: int = 0
    llm_queue_size: int = 0

    def to_dict(self) -> dict:
        """to dict.
            """
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
            "queued": self.improvements_queued,
            "patterns_used": self.patterns_used,
            "patterns_learned": self.patterns_learned,
            "status": self.status,
            "errors": self.errors[:5],
            "cross_file_issues": self.cross_file_issues,
            "llm_queue_size": self.llm_queue_size,
        }


# === IMPROVEMENT MEMORY ===


class ImprovementMemory:
    """Leert van elke cyclus en wordt slimmer. v2.0: decay rates."""

    def __init__(self, path: Path = MEMORY_FILE):
        self.path = path
        self.weights: dict[str, float] = dict(DEFAULT_WEIGHTS)
        self.patterns: list[LearnedPattern] = []
        self.history: list[ImprovementAttempt] = []
        self.total_cycles = 0
        self.llm_fixes_count = 0   # Nieuw: track LLM fixes
        self._load()

    def _load(self) -> None:
        """ load.
            """
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.weights.update(data.get("weights", {}))
                self.patterns = [LearnedPattern(**p) for p in data.get("patterns", [])]
                self.history = [ImprovementAttempt(**a) for a in data.get("history", [])]
                self.total_cycles = data.get("total_cycles", 0)
                self.llm_fixes_count = data.get("llm_fixes_count", 0)
            except (json.JSONDecodeError, TypeError):
                pass

    def save(self) -> None:
        """save.
            """
        data = {
            "weights": self.weights,
            "patterns": [p.to_dict() for p in self.patterns],
            "history": [a.to_dict() for a in self.history[-200:]],
            "total_cycles": self.total_cycles,
            "llm_fixes_count": self.llm_fixes_count,
            "last_updated": datetime.now().isoformat(),
            "version": "2.0",
        }
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def record_attempt(self, attempt: ImprovementAttempt) -> None:
        """record attempt.
        
            Args:
                attempt: Description.
        
            Returns:
                Description.
            """
        self.history.append(attempt)
        if attempt.fix_method == "llm_bridge":
            self.llm_fixes_count += 1

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
                # v2.0: adaptive learning rate based on success rate
                recent = [a for a in self.history[-20:]
                          if self._cat_to_weight(a.category) == cat_key]
                if recent:
                    sr = sum(1 for a in recent if a.success) / len(recent)
                    rate = 1.02 + sr * 0.05  # 1.02 - 1.07
                else:
                    rate = 1.05
                self.weights[cat_key] *= rate
                # Decay: niet-relevante weights licht verlagen
                for k in self.weights:
                    if k != cat_key and self.weights[k] > 0.5:
                        self.weights[k] *= 0.995

        self.total_cycles += 1
        self.save()

    def learn_pattern(self, category: str, description: str, code: str = "",
                      fix_method: str = "auto") -> str:
        """Register a learned pattern, or increment tries if it already exists."""
        pid = hashlib.md5(f"{category}:{description}".encode()).hexdigest()[:12]
        for p in self.patterns:
            if p.pattern_id == pid:
                p.times_tried += 1
                return pid
        pattern = LearnedPattern(pattern_id=pid, category=category,
                                  description=description, times_tried=1,
                                  last_used_cycle=self.total_cycles, code=code,
                                  fix_method=fix_method)
        self.patterns.append(pattern)
        self.save()
        return pid

    def get_best_patterns(self, category: str, top_n: int = 3) -> list[LearnedPattern]:
        """Return top-N patterns weighted by success_rate * improvement."""
        candidates = [p for p in self.patterns
                      if p.category == category and p.times_tried >= 2]
        candidates.sort(key=lambda p: p.success_rate * p.avg_improvement, reverse=True)
        return candidates[:top_n]

    def get_priority_categories(self) -> list[tuple[str, float]]:
        """Get priority categories.
            """
        impact: dict[str, float] = {}
        for key, weight in self.weights.items():
            cat_attempts = [a for a in self.history if self._weight_to_cat(key) in a.category]
            sr = sum(1 for a in cat_attempts if a.success) / max(1, len(cat_attempts))
            # v2.0: exploration bonus voor minder geprobeerde categorieën
            exploration_bonus = 1.0 / max(1, len(cat_attempts)) * 3.0
            impact[key] = weight * (1.0 + sr) + exploration_bonus
        return sorted(impact.items(), key=lambda x: x[1], reverse=True)

    @staticmethod
    def _cat_to_weight(category: str) -> str:
        """ cat to weight.
        
            Args:
                category: Description.
        
            Returns:
                Description.
            """
        mapping = {
            "syntax": "syntax_errors", "types": "type_coverage",
            "docs": "docstring_coverage", "code-quality": "e501_long_lines",
            "tests": "test_coverage", "complexity": "complexity",
            "dead-code": "dead_code", "dead_code": "dead_code",
            "security": "security_issues", "todos": "todo_markers",
            "refactor": "complexity", "performance": "complexity",
            "imports": "import_hygiene", "error_handling": "error_handling",
            "naming": "naming_conventions",
        }
        for k, v in mapping.items():
            if k in category:
                return v
        return "code-quality"

    @staticmethod
    def _weight_to_cat(key: str) -> str:
        """ weight to cat.
        
            Args:
                key: Description.
        
            Returns:
                Description.
            """
        rev = {
            "syntax_errors": "syntax", "type_coverage": "types",
            "docstring_coverage": "docs", "e501_long_lines": "code-quality",
            "e302_blank_lines": "code-quality", "test_coverage": "tests",
            "complexity": "complexity", "dead_code": "dead-code",
            "security_issues": "security", "todo_markers": "todos",
            "cross_file_duplication": "dead-code", "import_hygiene": "imports",
            "error_handling": "error_handling", "naming_conventions": "naming",
        }
        return rev.get(key, "code-quality")


# === SELF ANALYZER (v2.0) ===


class SelfAnalyzer:
    """Meet eigen codekwaliteit — v2.0 met cross-file analyse."""

    def __init__(self, workspace: Path, focus: str = "all"):
        self.workspace = workspace
        self.focus = focus
        self.metrics: list[MetricSnapshot] = []
        self._cross_file_duplicates: dict[str, list[str]] = defaultdict(list)

    def find_py_files(self) -> list[Path]:
        """Find py files.
            """
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
        """analyze file.
        
            Args:
                filepath: Description.
        
            Returns:
                Description.
            """
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

        # String literals tracking
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

        lines = content.splitlines()
        for i, line in enumerate(lines):
            if len(line) > 100 and (i + 1) not in string_lines:
                m.e501_count += 1

        for i, line in enumerate(lines):
            if i > 1 and line.startswith(("def ", "class ")):
                if lines[i - 1].strip() != "" or lines[i - 2].strip() != "":
                    m.e302_count += 1

        # Naming issues (non-snake_case functions)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                m.functions_total += 1
                # Type hints
                for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
                    if arg.annotation:
                        m.type_hints += 1
                if node.returns:
                    m.type_hints += 1
                # Docstrings
                if (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    m.docstrings += 1
                # Complexity
                branches = sum(1 for n in ast.walk(node)
                               if isinstance(n, (ast.If, ast.While, ast.For,
                                                 ast.ExceptHandler, ast.With,
                                                 ast.AsyncFor, ast.AsyncWith)))
                m.complexity_score += branches
                # Naming: skip unittest API methods (setUp, tearDown, etc.) en test_* methods
                if not re.match(r'^_?[a-z][a-z0-9_]*$', node.name) and not node.name.startswith('__'):
                    # unittest TestCase methods zijn altijd CamelCase — geen issue
                    if node.name not in ('setUp', 'tearDown', 'setUpClass', 'tearDownClass',
                                         'setUpModule', 'tearDownModule'):
                        m.naming_issues += 1

            # Error handlers
            if isinstance(node, (ast.Try, ast.TryStar)):
                m.error_handlers += 1

            # Import count
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                m.import_count += 1

        # TODOs
        m.todos = 0
        for i, line in enumerate(content.splitlines()):
            stripped = line.strip()
            if stripped.startswith("#") and re.search(r'(?:TODO|FIXME|HACK|BUG|XXX)', stripped):
                m.todos += 1

        # Test functions
        name = filepath.name
        if name.startswith("test_") or name.endswith("_test.py"):
            m.test_functions = sum(1 for node in ast.walk(tree)
                                   if isinstance(node, (ast.FunctionDef,)) and
                                   node.name.startswith("test_"))

        return m

    def scan_all(self) -> list[MetricSnapshot]:
        """Scan all.
            """
        self.metrics = []
        for fp in self.find_py_files():
            self.metrics.append(self.analyze_file(fp))
        return self.metrics

    def total_quality(self) -> float:
        """total quality.
            """
        if not self.metrics:
            return 0.0
        return sum(m.quality_score() for m in self.metrics) / len(self.metrics)

    def summary_stats(self) -> dict:
        """summary stats.
            """
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
            "docstrings": sum(m.docstrings for m in self.metrics),
            "type_hints": sum(m.type_hints for m in self.metrics),
            "todos": sum(m.todos for m in self.metrics),
            "naming_issues": sum(m.naming_issues for m in self.metrics),
            "error_handlers": sum(m.error_handlers for m in self.metrics),
            "quality_score": round(self.total_quality(), 3),
        }

    # ── Cross-file analyse (v2.0) ──────────────────────────────

    def find_duplicate_functions(self) -> list[dict]:
        """Vind functies die in meerdere bestanden voorkomen (copy-paste detectie)."""
        func_sigs: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for m in self.metrics:
            try:
                content = Path(m.file).read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Skip main() — elke tool heeft z'n eigen CLI entry point
                        if node.name == 'main':
                            continue
                        # Maak een signatuur op basis van naam + args
                        args = [a.arg for a in node.args.args]
                        sig = f"{node.name}({','.join(args)})"
                        # Alleen functies > 3 regels (geen eenregelige wrappers)
                        if hasattr(node, 'end_lineno') and hasattr(node, 'lineno'):
                            if node.end_lineno - node.lineno > 3:
                                func_sigs[sig].append((m.file, node.lineno))
            except SyntaxError:
                pass

        duplicates = []
        for sig, locations in func_sigs.items():
            if len(locations) > 1:
                files = list(set(loc[0] for loc in locations))
                if len(files) > 1:
                    duplicates.append({
                        "function": sig,
                        "files": files,
                        "locations": locations,
                    })
        return duplicates

    # Standaard bibliotheek imports die elke Python tool deelt — niet interessant
    STDLIB_TOP_LEVEL = frozenset({
        "sys", "os", "json", "re", "math", "time", "datetime", "pathlib",
        "collections", "typing", "hashlib", "subprocess", "argparse",
        "unittest", "tempfile", "shutil", "textwrap", "functools",
        "itertools", "logging", "io", "csv", "enum", "ast", "copy",
        "base64", "random", "string", "urllib", "http", "socket",
        "threading", "multiprocessing", "asyncio", "traceback",
        "warnings", "dataclasses", "abc", "ctypes", "struct",
        "importlib", "inspect", "pdb", "pickle", "sqlite3",
        "xml", "html", "configparser", "secrets", "getopt",
        "plistlib", "statistics", "uuid", "zipfile", "gzip",
        "tarfile", "glob", "fnmatch", "getpass", "platform",
        "signal", "mmap", "decimal", "fractions", "numbers",
    })
    # Interne ToolCase imports (shared by design)
    INTERNAL_IMPORTS = frozenset({"_protect", "i18n"})

    def find_similar_imports(self) -> list[dict]:
        """Vind bestanden met sterk overlappende imports (coupling detectie).
        
        Filtert stdlib imports uit — die deelt elke Python tool.
        Alleen third-party/project imports tellen voor echte coupling."""
        file_imports: dict[str, set[str]] = {}
        for m in self.metrics:
            try:
                content = Path(m.file).read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(content)
                imports = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            name = alias.name.split(".")[0]
                            if (name not in self.STDLIB_TOP_LEVEL
                                    and name not in self.INTERNAL_IMPORTS):
                                imports.add(name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            name = node.module.split(".")[0]
                            if (name not in self.STDLIB_TOP_LEVEL
                                    and name not in self.INTERNAL_IMPORTS):
                                imports.add(name)
                if imports:
                    file_imports[m.file] = imports
            except SyntaxError:
                pass

        similar = []
        files = list(file_imports.keys())
        for i in range(len(files)):
            for j in range(i + 1, len(files)):
                if file_imports[files[i]] and file_imports[files[j]]:
                    overlap = file_imports[files[i]] & file_imports[files[j]]
                    min_size = min(len(file_imports[files[i]]), len(file_imports[files[j]]))
                    # Alleen rapporteren bij >90% overlap in niet-stdlib imports, minimaal 2
                    if min_size >= 2 and len(overlap) / min_size > 0.90:
                        similar.append({
                            "file_a": files[i],
                            "file_b": files[j],
                            "shared_imports": sorted(overlap),
                            "overlap_ratio": round(len(overlap) / min_size, 2),
                        })
        return similar


# === IMPROVEMENT PLANNER (v2.0) ===


class ImprovementPlanner:
    def __init__(self, memory: ImprovementMemory, focus: str = "all",
                 analyzer: Optional[SelfAnalyzer] = None):
        self.memory = memory
        self.focus = focus
        self.analyzer = analyzer

    def plan(self, metrics: list[MetricSnapshot], cycle: int) -> list[ImprovementAttempt]:
        """Generate prioritized improvement attempts — split auto vs LLM."""
        attempts: list[ImprovementAttempt] = []
        seen = set()

        def add(a: ImprovementAttempt) -> None:
            """add.
            
                Args:
                    a: Description.
            
                Returns:
                    Description.
                """
            key = f"{a.category}:{a.file}:{a.description[:60]}"
            if key not in seen:
                seen.add(key)
                attempts.append(a)

        allowed = FOCUS_TO_ISSUE_TYPES.get(self.focus, LLM_FIXABLE)

        # Auto-fixable: E501/E302
        if self.focus in ("all", "code-quality"):
            for m in metrics:
                if m.e501_count > 3:
                    add(ImprovementAttempt(cycle=cycle, category="code-quality",
                        file=m.file, fix_method="auto",
                        description=f"E501: {m.e501_count} lange regels in {Path(m.file).name}",
                        metric_before=m.quality_score()))
                if m.e302_count > 3:
                    add(ImprovementAttempt(cycle=cycle, category="code-quality",
                        file=m.file, fix_method="auto",
                        description=f"E302: {m.e302_count} ontbrekende blank lines",
                        metric_before=m.quality_score()))

        # LLM: Docs
        if "docs" in allowed and self.focus in ("all", "docs"):
            for m in metrics:
                if m.functions_total > 0 and m.docstrings < m.functions_total:
                    missing = m.functions_total - m.docstrings
                    add(ImprovementAttempt(cycle=cycle, category="docs",
                        file=m.file, fix_method="llm_bridge",
                        description=f"Docs: {missing}/{m.functions_total} functies missen docstring in {Path(m.file).name}",
                        metric_before=m.quality_score()))

        # LLM: Types
        if "types" in allowed and self.focus in ("all", "types"):
            for m in metrics:
                if m.functions_total > 0:
                    expected_hints = m.functions_total * 2 + m.functions_total  # args + returns
                    if m.type_hints < expected_hints * 0.3:
                        add(ImprovementAttempt(cycle=cycle, category="types",
                            file=m.file, fix_method="llm_bridge",
                            description=f"Types: {m.type_hints} hints voor {m.functions_total} functies in {Path(m.file).name}",
                            metric_before=m.quality_score()))

        # LLM: TODOs
        if self.focus in ("all", "code-quality"):
            for m in metrics:
                if m.todos > 5:
                    add(ImprovementAttempt(cycle=cycle, category="todos",
                        file=m.file, fix_method="llm_bridge",
                        description=f"TODOs: {m.todos} markers in {Path(m.file).name}",
                        metric_before=m.quality_score()))

        # LLM: Naming
        if "naming" in allowed and self.focus in ("all", "refactor", "code-quality"):
            for m in metrics:
                if m.naming_issues > 2:
                    add(ImprovementAttempt(cycle=cycle, category="naming",
                        file=m.file, fix_method="llm_bridge",
                        description=f"Naming: {m.naming_issues} non-Pythonic names in {Path(m.file).name}",
                        metric_before=m.quality_score()))

        # LLM: Error handling
        if "error_handling" in allowed and self.focus in ("all", "bugs", "architecture"):
            for m in metrics:
                if m.functions_total > 10 and m.error_handlers < m.functions_total * 0.2:
                    add(ImprovementAttempt(cycle=cycle, category="error_handling",
                        file=m.file, fix_method="llm_bridge",
                        description=f"Error handling: {m.error_handlers} handlers voor {m.functions_total} functies",
                        metric_before=m.quality_score()))

        # Cross-file duplicates (LLM)
        if self.analyzer and self.focus in ("all", "architecture", "refactor"):
            dups = self.analyzer.find_duplicate_functions()
            for dup in dups[:5]:  # Max 5 duplicate groups
                files_list = ", ".join(Path(f).name for f in dup["files"][:3])
                add(ImprovementAttempt(cycle=cycle, category="dead_code",
                    file=dup["files"][0], fix_method="llm_bridge",
                    description=f"Cross-file duplicate: {dup['function']} in {files_list}",
                    metric_before=0.5))

        # Prioriteer: memory-weights + metric
        priority_cats = self.memory.get_priority_categories()
        cat_order = {cat: i for i, (cat, _) in enumerate(priority_cats)}

        def sort_key(a: ImprovementAttempt) -> tuple:
            """sort key.
            
                Args:
                    a: Description.
            
                Returns:
                    Description.
                """
            return (-cat_order.get(self.memory._cat_to_weight(a.category), 50),
                    -(a.metric_before or 0))

        attempts.sort(key=sort_key)
        return attempts[:25]  # Max 25 per cycle


# === IMPROVEMENT EXECUTOR (v2.0) ===


class ImprovementExecutor:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.backups: dict[str, str] = {}
        self._bridge: Optional[Any] = None  # Lazy init

    @property
    def bridge(self):
        """bridge.
            """
        if self._bridge is None and LLMBridge is not None:
            self._bridge = LLMBridge(self.workspace)
        return self._bridge

    def create_backup(self, filepath: Path) -> Optional[str]:
        """Create backup.
        
            Args:
                filepath: Description.
        
            Returns:
                Description.
            """
        if not filepath.exists():
            return None
        backup_dir = self.workspace / ".rsi_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        bak_name = f"{filepath.name}.{ts}.rsi_bak"
        bak_path = backup_dir / bak_name
        shutil.copy2(str(filepath), str(bak_path))
        self.backups[str(filepath)] = str(bak_path)
        return str(bak_path)

    def rollback(self, filepath: Path) -> bool:
        """rollback.
        
            Args:
                filepath: Description.
        
            Returns:
                Description.
            """
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

            string_lines: set[int] = set()
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                            for ln in range(node.lineno, node.end_lineno + 1):
                                string_lines.add(ln)
                    elif isinstance(node, ast.JoinedStr):
                        if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                            for ln in range(node.lineno, node.end_lineno + 1):
                                string_lines.add(ln)
            except SyntaxError:
                pass

            new_lines = []
            fixed = 0
            for i, line in enumerate(lines):
                line_no = i + 1
                stripped = line.rstrip()
                if len(stripped) <= 100 or line_no in string_lines:
                    new_lines.append(line)
                    continue

                best_break = -1
                for bp in [90, 80, 70]:
                    idx = stripped.rfind(", ", 0, bp)
                    if idx > 20:
                        best_break = idx + 1
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
        """Apply e302 fix.
        
            Args:
                filepath: Description.
        
            Returns:
                Description.
            """
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

    # ── LLM Bridge Methods ────────────────────────────────────

    def submit_to_llm(self, attempt: ImprovementAttempt) -> Optional[str]:
        """Submit een fix-attempt naar de LLM bridge queue."""
        if not self.bridge:
            return None

        filepath = Path(attempt.file)
        context = {
            "file_path": str(filepath),
            "category": attempt.category,
            "description": attempt.description,
        }

        # Voeg code context toe
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                # Beperk context tot relevante delen
                if len(content) > 8000:
                    context["code_snippet"] = content[:4000] + "\n...\n" + content[-4000:]
                else:
                    context["code_snippet"] = content
                context["file_lines"] = len(content.splitlines())
            except Exception:
                pass

        # Voeg cross-file info toe indien relevant
        if attempt.category == "dead_code" and "Cross-file" in attempt.description:
            context["cross_file"] = True

        request_id = self.bridge.submit_fix(
            file_path=attempt.file,
            issue_type=attempt.category,
            description=attempt.description,
            context=context,
            priority=2.0 if attempt.category in ("security", "docs", "types") else 1.0,
        )

        if request_id:
            attempt.bridge_request_id = request_id
            attempt.fix_method = "llm_bridge"

        return request_id

    def process_llm_results(self, attempts: list[ImprovementAttempt]) -> list[ImprovementAttempt]:
        """Lees LLM bridge resultaten en update attempts."""
        if not self.bridge:
            return attempts

        for attempt in attempts:
            if attempt.fix_method == "llm_bridge" and attempt.bridge_request_id:
                result = self.bridge.get_result(attempt.bridge_request_id)
                if result:
                    attempt.success = result.success
                    attempt.error = result.error if not result.success else ""
                    if result.success:
                        attempt.description += f" [LLM: {result.changes_made[:50]}]"

        return attempts

    def get_llm_queue_summary(self) -> dict:
        """Krijg een samenvatting van de LLM queue."""
        if not self.bridge:
            return {"pending": 0, "done": 0, "failed": 0}
        return {
            "pending": self.bridge.count_pending(),
            "done": self.bridge.count_done(),
            "failed": self.bridge.count_failed(),
        }


# === EVALUATOR ===


class Evaluator:
    def __init__(self, workspace: Path):
        self.workspace = workspace

    def compile_check(self) -> tuple[bool, list[str]]:
        """compile check.
            """
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
        """test check.
            """
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
        """evaluate.
            """
        compile_ok, compile_errs = self.compile_check()
        test_ok, test_details = self.test_check()
        return {
            "compile_ok": compile_ok,
            "compile_errors": compile_errs,
            "test_ok": test_ok,
            "test_details": test_details,
            "passed": compile_ok and test_ok,
        }


# === RECURSIVE LOOP (v2.0) ===


class RecursiveSelfImprove:
    """Main RSI loop v2.0 — met LLM bridge integratie."""

    def __init__(self, workspace: Path, focus: str = "all",
                 dry_run: bool = False, no_report: bool = False,
                 memory_path: Optional[Path] = None,
                 llm_mode: str = "auto"):
        """
        llm_mode:
            "auto"       - Auto-fixes direct, LLM-fixes naar queue
            "auto-only"  - Alleen auto-fixes, geen LLM
            "llm-queue"  - Alleen queue vullen, geen auto-fixes toepassen
            "llm-eval"   - Alleen queue resultaten evalueren
        """
        self.workspace = workspace
        self.focus = focus
        self.dry_run = dry_run
        self.no_report = no_report
        self.llm_mode = llm_mode
        self.memory = ImprovementMemory(
            memory_path or (workspace / ".rsi_memory.json")
        )
        self.analyzer = SelfAnalyzer(workspace, focus)
        self.planner = ImprovementPlanner(self.memory, focus, self.analyzer)
        self.executor = ImprovementExecutor(workspace)
        self.evaluator = Evaluator(workspace)
        self.reports: list[CycleReport] = []
        self.evolution_log: list[str] = []

    def run_cycle(self, cycle: int) -> CycleReport:
        """Run cycle.
        
            Args:
                cycle: Description.
        
            Returns:
                Description.
            """
        print()
        print(_c(f"  {'='*56}", "cyan"))
        print(_c(f"  RSI v2.0 — Cycle {cycle} — Focus: {self.focus.upper()}", "cyan"))
        print(_c(f"  LLM Mode: {self.llm_mode}", "dim"))
        if not self.dry_run:
            print(_c(f"     Memory: {len(self.memory.patterns)} patterns, "
                    f"{len(self.memory.history)} attempts, "
                    f"{self.memory.llm_fixes_count} LLM fixes", "dim"))
        print(_c(f"  {'='*56}", "cyan"))

        start_time = time.time()
        report = CycleReport(cycle=cycle, focus=self.focus)

        # STEP 1: ANALYSE
        print(_c(f"\n  1. ANALYSE — Meten van codekwaliteit...", "bold"))
        metrics = self.analyzer.scan_all()
        report.metrics = metrics
        report.files_analyzed = len(metrics)
        report.total_quality_before = self.analyzer.total_quality()
        stats = self.analyzer.summary_stats()

        print(f"     Files: {stats.get('files',0)}  |  Lines: {stats.get('lines',0)}  |  "
              f"E501: {stats.get('e501_total',0)}")
        print(f"     Functions: {stats.get('functions_total',0)}  |  "
              f"Docs: {stats.get('docstrings',0)}  |  "
              f"Types: {stats.get('type_hints',0)}")
        print(f"     Quality: {stats.get('quality_score', 0):.4f}")

        # ── Cross-file analyse (v2.0) ──
        print(_c(f"\n  1b. CROSS-FILE — Zoeken naar duplicaten...", "bold"))
        dups = self.analyzer.find_duplicate_functions()
        similar = self.analyzer.find_similar_imports()
        report.cross_file_issues = len(dups) + len(similar)
        if dups:
            print(f"     🔄 {len(dups)} duplicate functies over bestanden heen")
            for d in dups[:3]:
                files = ", ".join(Path(f).name for f in d["files"][:3])
                print(f"        • {d['function']} in [{files}]")
        if similar:
            print(f"     📦 {len(similar)} bestandsparen met sterke import-overlap")

        # STEP 2: REFLECT
        print(_c(f"\n  2. REFLECT — Bepalen van prioriteiten...", "bold"))
        priorities = self.memory.get_priority_categories()[:6]
        if priorities:
            max_impact = max(p[1] for p in priorities) if priorities else 1
            for cat, impact in priorities:
                bar_len = min(int(impact / max_impact * 12), 12)
                bar = "█" * bar_len + "░" * (12 - bar_len)
                print(f"       [{bar}] {cat:<30s} {impact:.1f}")

        # STEP 3: GENERATE & PLAN
        print(_c(f"\n  3. PLAN — Verbeteringen plannen...", "bold"))
        attempts = self.planner.plan(metrics, cycle)
        report.improvements_attempted = len(attempts)

        auto_attempts = [a for a in attempts if a.fix_method == "auto"]
        llm_attempts = [a for a in attempts if a.fix_method == "llm_bridge"]
        print(f"     {len(auto_attempts)} auto-fixable  |  {len(llm_attempts)} LLM-required")

        # STEP 4: EXECUTE
        if not self.dry_run and self.llm_mode != "llm-eval":
            # Auto fixes
            if self.llm_mode != "llm-queue":
                print(_c(f"\n  4a. AUTO-FIX — Directe fixes toepassen...", "bold"))
                for attempt in auto_attempts:
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

                    attempt.success = success
                    if success:
                        report.improvements_succeeded += 1
                        print(f"       + {result_msg}")
                        self.memory.learn_pattern(attempt.category, attempt.description,
                                                  fix_method="auto")
                    else:
                        if result_msg:
                            print(f"       . {result_msg}")
                    report.attempts.append(attempt)

            # LLM Queue
            if self.llm_mode != "auto-only":
                print(_c(f"\n  4b. LLM-QUEUE — Complexe fixes naar Hermes...", "bold"))
                queued = 0
                for attempt in llm_attempts:
                    rid = self.executor.submit_to_llm(attempt)
                    if rid:
                        queued += 1
                        report.attempts.append(attempt)
                report.improvements_queued = queued
                qs = self.executor.get_llm_queue_summary()
                report.llm_queue_size = qs["pending"]
                print(f"     {queued} fixes in queue (totaal pending: {qs['pending']})")
                if queued > 0:
                    print(_c(f"     ⏳ Wacht op Hermes om {queued} fixes te verwerken...", "yellow"))

        # STEP 5: EVALUATE
        print(_c(f"\n  5. EVALUATE — Controleren van resultaten...", "bold"))
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
        elif report.improvements_queued > 0:
            print(f"     . Auto-fixes OK, LLM fixes in queue — Hermes moet nog verwerken")
            report.status = "pending_llm"
        else:
            print(f"     . Geen wijzigingen om te evalueren")
            report.status = "completed" if report.status != "pending_llm" else report.status

        # STEP 6: RE-MEASURE
        print(_c(f"\n  6. METEN — Opnieuw meten van kwaliteit...", "bold"))
        metrics_after = self.analyzer.scan_all()
        report.total_quality_after = self.analyzer.total_quality()
        delta = report.total_quality_after - report.total_quality_before
        d_str = _c(f"+{delta:.4f}", "green") if delta > 0 else (
            _c(f"{delta:.4f}", "red") if delta < 0 else _c(f"{delta:.4f}", "dim"))
        print(f"     Kwaliteit: {report.total_quality_before:.4f} → "
              f"{report.total_quality_after:.4f} ({d_str})")

        # STEP 7: LEARN
        print(_c(f"\n  7. LEARN — Opslaan van geleerde lessen...", "bold"))
        learned = 0
        for attempt in report.attempts:
            if attempt.success:
                self.memory.record_attempt(attempt)
                learned += 1
        report.patterns_learned = learned
        report.patterns_used = len(self.memory.patterns)
        print(f"     {learned} pogingen opgeslagen, totaal {len(self.memory.patterns)} patronen")
        if self.memory.llm_fixes_count > 0:
            print(f"     {self.memory.llm_fixes_count} LLM fixes totaal")

        report.duration_s = round(time.time() - start_time, 1)
        self.evolution_log.append(
            f"Cycle {cycle}: {report.total_quality_before:.4f} → "
            f"{report.total_quality_after:.4f} ({delta:+.4f}), "
            f"{report.improvements_succeeded}/{report.improvements_attempted} ok, "
            f"{report.improvements_queued} queued, "
            f"{report.duration_s}s"
        )
        if report.status not in ("rolled_back", "pending_llm"):
            report.status = "completed"
        self.reports.append(report)
        return report

    def run(self, cycles: int = 1) -> list[CycleReport]:
        """run.
        
            Args:
                cycles: Description.
        
            Returns:
                Description.
            """
        mode_map = {
            "auto": _c("AUTO + LLM", "cyan"),
            "auto-only": _c("AUTO-ONLY", "yellow"),
            "llm-queue": _c("QUEUE-ONLY", "blue"),
            "llm-eval": _c("EVAL-ONLY", "magenta"),
        }
        mode_str = mode_map.get(self.llm_mode, self.llm_mode)
        if self.dry_run:
            mode_str = _c("DRY-RUN", "yellow")

        print()
        print(_c(f"  {'='*54}", "magenta"))
        print(_c(f"  RECURSIVE SELF-IMPROVEMENT v2.0", "magenta"))
        print(_c(f"  Mode: {mode_str}  |  Cycles: {cycles}  |  Focus: {self.focus.upper()}", "magenta"))
        print(_c(f"  Workspace: {self.workspace}", "magenta"))
        print(_c(f"  Memory: {len(self.memory.patterns)} patterns, "
                f"{len(self.memory.history)} past attempts, "
                f"{self.memory.llm_fixes_count} LLM fixes", "magenta"))
        print(_c(f"  {'='*54}", "magenta"))

        for cycle in range(1, cycles + 1):
            report = self.run_cycle(cycle)
            if report.status == "rolled_back":
                print(_c(f"\n  ⚠ Rollback — stoppen met verdere cycli", "yellow"))
                break

        # Final report
        self._print_final_report()

        return self.reports

    def run_llm_eval(self) -> CycleReport:
        """Evalueer LLM bridge resultaten en leer ervan."""
        print()
        print(_c(f"  {'='*54}", "magenta"))
        print(_c(f"  RSI v2.0 — LLM QUEUE EVALUATIE", "magenta"))
        print(_c(f"  {'='*54}", "magenta"))

        report = CycleReport(cycle=self.memory.total_cycles + 1, focus="llm-eval")
        start_time = time.time()

        # Lees queue stats
        qs = self.executor.get_llm_queue_summary()
        print(f"\n  Queue: {qs['pending']} pending | {qs['done']} done | {qs['failed']} failed")

        # Lees alle done results
        done = self.executor.bridge.list_done() if self.executor.bridge else []
        failed = self.executor.bridge.list_failed() if self.executor.bridge else []

        learned = 0
        for result in done:
            if result.success:
                # Leer van succesvolle LLM fixes
                self.memory.learn_pattern(
                    category="docs",  # Placeholder — zou uit result moeten komen
                    description=f"LLM fix: {result.changes_made[:80]}",
                    fix_method="llm_bridge",
                )
                self.memory.record_attempt(ImprovementAttempt(
                    cycle=report.cycle,
                    category="docs",
                    file=result.file_path,
                    description=result.changes_made[:80],
                    success=True,
                    fix_method="llm_bridge",
                    bridge_request_id=result.request_id,
                    metric_before=0.5,
                    metric_after=0.8,
                    duration_ms=result.duration_ms,
                ))
                learned += 1

        for result in failed:
            self.memory.record_attempt(ImprovementAttempt(
                cycle=report.cycle,
                category="unknown",
                file=result.file_path,
                description=result.error[:80] or "LLM fix failed",
                success=False,
                fix_method="llm_bridge",
                bridge_request_id=result.request_id,
                error=result.error,
            ))

        report.improvements_succeeded = learned
        report.improvements_failed = len(failed)
        report.patterns_learned = learned
        report.patterns_used = len(self.memory.patterns)
        report.duration_s = round(time.time() - start_time, 1)
        report.status = "completed"
        report.llm_queue_size = qs["pending"]

        print(f"\n  ✅ {learned} LLM fixes geleerd")
        print(f"  ❌ {len(failed)} gefaald")
        print(f"  📊 Totaal patronen: {len(self.memory.patterns)}")
        print(f"  🤖 LLM fixes totaal: {self.memory.llm_fixes_count}")

        self.reports.append(report)
        return report

    def _print_final_report(self) -> None:
        """ print final report.
            """
        print()
        print(_c(f"  {'='*54}", "magenta"))
        print(_c(f"  RSI v2.0 — EINDRAPPORT", "magenta"))
        print(_c(f"  {'='*54}", "magenta"))

        if self.reports:
            first_q = self.reports[0].total_quality_before
            last_q = self.reports[-1].total_quality_after
            total_delta = last_q - first_q
            arrow = _c("▲", "green") if total_delta > 0 else (
                _c("▼", "red") if total_delta < 0 else _c("─", "dim"))

            print(f"\n  {'Cycle':<7s} {'Voor':>8s} {'Na':>8s} {'Delta':>8s}  {'Auto':>4s} {'LLM':>4s}  Status")
            print(f"  {'─'*55}")
            for r in self.reports:
                d = r.total_quality_after - r.total_quality_before
                ds = _c(f"{d:+.4f}", "green") if d > 0 else (
                    _c(f"{d:.4f}", "red") if d < 0 else _c(f"{d:.4f}", "dim"))
                print(f"  #{r.cycle:<4d}  {r.total_quality_before:.4f}  {r.total_quality_after:.4f}  "
                      f"{ds}  {r.improvements_succeeded:>3d}  {r.improvements_queued:>3d}  "
                      f"{r.status.upper()}")

            total_auto = sum(r.improvements_succeeded for r in self.reports)
            total_llm = sum(r.improvements_queued for r in self.reports)
            print(f"\n  {arrow} Totaal: {first_q:.4f} → {last_q:.4f} ({total_delta:+.4f})")
            print(f"  Auto-fixes: {total_auto}  |  LLM-queued: {total_llm}")
            print(f"  Geleerde patronen: {len(self.memory.patterns)}")
            print(f"  LLM fixes totaal: {self.memory.llm_fixes_count}")
            print(f"  Memory: {self.memory.path}")

            if total_llm > 0:
                print(_c(f"\n  ⏳ {total_llm} fixes wachten in LLM queue op Hermes!", "yellow"))
                print(_c(f"  👉 Run: python rsi_llm_bridge.py list-pending", "cyan"))

            if not self.no_report and not self.dry_run and any(r.status == "completed" or r.status == "pending_llm" for r in self.reports):
                report_dir = self.workspace / ".rsi_reports"
                report_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                rf = report_dir / f"rsi_report_{ts}.json"
                rf.write_text(json.dumps([r.to_dict() for r in self.reports],
                                         indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"  JSON Report: {rf}")

    def get_json_report(self) -> dict:
        """Get json report.
            """
        return {
            "version": "2.0",
            "focus": self.focus,
            "dry_run": self.dry_run,
            "llm_mode": self.llm_mode,
            "cycles_completed": len(self.reports),
            "memory_patterns": len(self.memory.patterns),
            "memory_attempts": len(self.memory.history),
            "llm_fixes_count": self.memory.llm_fixes_count,
            "reports": [r.to_dict() for r in self.reports],
            "evolution": self.evolution_log,
        }


# === MAIN CLI ===


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="RSI v2.0 — Recursive Self-Improvement met LLM Bridge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("path", nargs="?", default=".", help="ToolCase directory")
    parser.add_argument("--cycles", "-c", type=int, default=1,
                        help=f"Aantal cycli (max {MAX_CYCLES})")
    parser.add_argument("--focus", "-f",
                        choices=["all", "types", "docs", "code-quality", "tests",
                                 "security", "refactor", "performance", "architecture",
                                 "dead-code", "bugs"],
                        default="all", help="Focus area (uitgebreid in v2.0)")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Alleen analyse, geen wijzigingen")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--no-report", action="store_true",
                        help="Geen rapport of memory opslaan")
    parser.add_argument("--learn-from", metavar="FILE",
                        help="Laad memory uit bestand")

    # v2.0 LLM bridge modi
    parser.add_argument("--auto-only", action="store_true",
                        help="Alleen auto-fixes, geen LLM queue")
    parser.add_argument("--llm-queue", action="store_true",
                        help="Alleen LLM queue vullen, geen auto-fixes")
    parser.add_argument("--llm-eval", action="store_true",
                        help="Evalueer LLM queue resultaten en leer ervan")

    parser.add_argument("--version", action="version",
                        version=f"recursive_self_improve.py v{__version__}")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f"Error: '{args.path}' bestaat niet", file=sys.stderr)
        sys.exit(1)

    # Bepaal LLM mode
    if args.auto_only:
        llm_mode = "auto-only"
    elif args.llm_queue:
        llm_mode = "llm-queue"
    elif args.llm_eval:
        llm_mode = "llm-eval"
    else:
        llm_mode = "auto"

    rsi = RecursiveSelfImprove(
        workspace=target, focus=args.focus,
        dry_run=args.dry_run, no_report=args.no_report,
        memory_path=Path(args.learn_from).resolve() if args.learn_from else None,
        llm_mode=llm_mode,
    )

    if args.llm_eval:
        rsi.run_llm_eval()
    else:
        cycles = min(args.cycles, MAX_CYCLES)
        rsi.run(cycles=cycles)

    if args.json:
        print(json.dumps(rsi.get_json_report(), indent=2, ensure_ascii=False))

    # Exit code
    if rsi.reports:
        last = rsi.reports[-1]
        if last.status == "rolled_back":
            sys.exit(2)
        elif last.improvements_succeeded > 0 or last.improvements_queued > 0:
            sys.exit(0)
        elif last.total_quality_after >= 0.95:
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
