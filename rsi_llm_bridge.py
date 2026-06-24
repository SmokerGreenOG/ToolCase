#!/usr/bin/env python3
"""rsi_llm_bridge.py — RSI ↔ Hermes LLM Bridge (v2.0)

De brug tussen de RSI analyse-engine en Hermes (de LLM agent) voor
intelligente code fixes — zonder API keys.

Flow:
  1. RSI analyseert → schrijft fix-requests naar .rsi_fix_queue/pending/
  2. Hermes leest de queue → voert fixes uit met zijn tools
  3. Hermes schrijft resultaten naar .rsi_fix_queue/done/
  4. RSI leest resultaten → valideert → leert

Queue structuur:
  .rsi_fix_queue/
  ├── pending/     # Requests die wachten op Hermes
  ├── done/        # Afgewerkte requests (resultaat)
  ├── failed/      # Gefaalde requests
  └── queue_state.json  # Meta-info over de queue

Gebruik (vanuit RSI):
    bridge = LLMBridge(workspace)
    request_id = bridge.submit_fix(
        file_path="tool.py",
        issue_type="docs",
        description="Functie calculate() mist docstring",
        context={"function_name": "calculate", "code": "def calculate(x):..."},
    )
    # ... Hermes verwerkt de request ...
    result = bridge.get_result(request_id)
    if result["success"]:
        bridge.learn_from_result(request_id, result)

Gebruik (CLI — voor Hermes om queue te bekijken):
    python rsi_llm_bridge.py list-pending     # Toon alle pending
    python rsi_llm_bridge.py show <id>        # Toon request details
    python rsi_llm_bridge.py list-done        # Toon afgewerkte
    python rsi_llm_bridge.py stats            # Queue statistieken
"""

from __future__ import annotations

__maker__ = "SmokerGreenOG"
__version__ = "2.0.0"

import _protect
import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# ── Constants ─────────────────────────────────────────────────

QUEUE_DIR_NAME = ".rsi_fix_queue"
MAX_QUEUE_SIZE = 50
REQUEST_VERSION = "2.0"

# Issue types die de LLM kan fixen
LLM_FIXABLE = frozenset({
    "docs",         # Docstrings schrijven
    "types",        # Type hints toevoegen
    "refactor",     # Code refactoring
    "security",     # Security fixes
    "dead_code",    # Dead code removal
    "tests",        # Test generatie
    "complexity",   # Complexiteit verlagen
    "naming",       # Naming conventions fixen
    "imports",      # Import optimalisatie
    "error_handling",  # Error handling toevoegen
    "performance",  # Performance verbeteringen
    "bugfix",       # Bug fixes
})

# Issue types die de RSI zelf kan fixen (geen LLM nodig)
AUTO_FIXABLE = frozenset({
    "e501",         # Lange regels wrappen
    "e302",         # Blank lines
    "trailing_ws",  # Trailing whitespace
    "newline_eof",  # Newline at EOF
})


# ── Data Classes ──────────────────────────────────────────────

@dataclass


class FixRequest:
    """Een fix-request voor Hermes om te verwerken."""
    id: str = ""
    timestamp: str = ""
    file_path: str = ""
    issue_type: str = ""          # docs, types, refactor, security, etc.
    description: str = ""         # Wat moet er gefixt worden
    priority: float = 0.0         # Prioriteit (hogere = belangrijker)
    context: dict = field(default_factory=dict)
    # context kan bevatten:
    #   - function_name: str
    #   - code_snippet: str (de relevante code)
    #   - line_start: int
    #   - line_end: int
    #   - expected_behavior: str
    #   - current_metrics: dict
    #   - dependencies: list[str]
    status: str = "pending"      # pending | done | failed

    def to_dict(self) -> dict:
        """to dict.
            """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FixRequest":
        """from dict.
        
            Args:
                data: Description.
        
            Returns:
                Description.
            """
        return cls(**{k: data.get(k) for k in [
            "id", "timestamp", "file_path", "issue_type",
            "description", "priority", "context", "status"
        ]})


@dataclass


class FixResult:
    """Resultaat van een door Hermes uitgevoerde fix."""
    request_id: str = ""
    timestamp: str = ""
    success: bool = False
    file_path: str = ""
    changes_made: str = ""         # Beschrijving van wat er veranderd is
    diff_summary: str = ""         # Samenvatting van de diff
    metrics_before: dict = field(default_factory=dict)
    metrics_after: dict = field(default_factory=dict)
    error: str = ""               # Eventuele foutmelding
    tokens_used: int = 0           # Schatting van token gebruik
    duration_ms: int = 0

    def to_dict(self) -> dict:
        """to dict.
            """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FixResult":
        """from dict.
        
            Args:
                data: Description.
        
            Returns:
                Description.
            """
        return cls(**{k: data.get(k) for k in [
            "request_id", "timestamp", "success", "file_path",
            "changes_made", "diff_summary", "metrics_before",
            "metrics_after", "error", "tokens_used", "duration_ms"
        ]})


@dataclass


class QueueState:
    """Meta-informatie over de fix queue."""
    total_requests: int = 0
    total_done: int = 0
    total_failed: int = 0
    total_success: int = 0
    total_tokens: int = 0
    avg_duration_ms: float = 0.0
    last_activity: str = ""
    issues_fixed_by_type: dict = field(default_factory=dict)
    version: str = REQUEST_VERSION

    def to_dict(self) -> dict:
        """to dict.
            """
        return asdict(self)


# ── LLM Bridge ────────────────────────────────────────────────


class LLMBridge:
    """De brug tussen RSI en Hermes voor intelligente code fixes."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.queue_dir = self.workspace / QUEUE_DIR_NAME
        self.pending_dir = self.queue_dir / "pending"
        self.done_dir = self.queue_dir / "done"
        self.failed_dir = self.queue_dir / "failed"
        self.state_file = self.queue_dir / "queue_state.json"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Maak de queue directory structuur aan."""
        for d in [self.queue_dir, self.pending_dir, self.done_dir, self.failed_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _generate_id(self, file_path: str, issue_type: str, description: str) -> str:
        """Genereer een uniek request ID."""
        raw = f"{file_path}:{issue_type}:{description}:{time.time_ns()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def submit_fix(self, file_path: str, issue_type: str,
                   description: str, context: dict = None,
                   priority: float = 1.0) -> Optional[str]:
        """Submit een fix-request naar de queue.

        Returns het request ID, of None als de queue vol is.
        """
        # Check queue size
        pending = list(self.pending_dir.glob("*.json"))
        if len(pending) >= MAX_QUEUE_SIZE:
            print(f"  ⚠ Queue vol ({MAX_QUEUE_SIZE} pending). Wacht op verwerking.")
            return None

        req_id = self._generate_id(file_path, issue_type, description)
        request = FixRequest(
            id=req_id,
            timestamp=datetime.now().isoformat(),
            file_path=str(file_path),
            issue_type=issue_type,
            description=description,
            priority=priority,
            context=context or {},
            status="pending",
        )

        req_file = self.pending_dir / f"{req_id}.json"
        req_file.write_text(
            json.dumps(request.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._update_state()
        return req_id

    def get_result(self, request_id: str) -> Optional[FixResult]:
        """Haal het resultaat van een verwerkte request op."""
        done_file = self.done_dir / f"{request_id}.json"
        if done_file.exists():
            try:
                data = json.loads(done_file.read_text(encoding="utf-8"))
                return FixResult.from_dict(data)
            except (json.JSONDecodeError, TypeError):
                return None

        failed_file = self.failed_dir / f"{request_id}.json"
        if failed_file.exists():
            try:
                data = json.loads(failed_file.read_text(encoding="utf-8"))
                return FixResult.from_dict(data)
            except (json.JSONDecodeError, TypeError):
                return None

        return None  # Nog in behandeling

    def mark_done(self, request_id: str, result: FixResult) -> None:
        """Markeer een request als afgewerkt (wordt aangeroepen door Hermes)."""
        req_file = self.pending_dir / f"{request_id}.json"
        if req_file.exists():
            req_file.unlink()

        target_dir = self.done_dir if result.success else self.failed_dir
        out_file = target_dir / f"{request_id}.json"
        out_file.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._update_state()

    def list_pending(self) -> list[FixRequest]:
        """Lijst alle pending requests op (gesorteerd op prioriteit)."""
        requests = []
        for rf in sorted(self.pending_dir.glob("*.json")):
            try:
                data = json.loads(rf.read_text(encoding="utf-8"))
                requests.append(FixRequest.from_dict(data))
            except (json.JSONDecodeError, TypeError):
                pass
        requests.sort(key=lambda r: -r.priority)
        return requests

    def list_done(self) -> list[FixResult]:
        """Lijst alle afgewerkte resultaten op."""
        results = []
        for rf in sorted(self.done_dir.glob("*.json")):
            try:
                data = json.loads(rf.read_text(encoding="utf-8"))
                results.append(FixResult.from_dict(data))
            except (json.JSONDecodeError, TypeError):
                pass
        return results

    def list_failed(self) -> list[FixResult]:
        """Lijst alle gefaalde resultaten op."""
        results = []
        for rf in sorted(self.failed_dir.glob("*.json")):
            try:
                data = json.loads(rf.read_text(encoding="utf-8"))
                results.append(FixResult.from_dict(data))
            except (json.JSONDecodeError, TypeError):
                pass
        return results

    def count_pending(self) -> int:
        """Aantal pending requests."""
        return len(list(self.pending_dir.glob("*.json")))

    def count_done(self) -> int:
        """Aantal afgewerkte requests."""
        return len(list(self.done_dir.glob("*.json")))

    def count_failed(self) -> int:
        """Aantal gefaalde requests."""
        return len(list(self.failed_dir.glob("*.json")))

    def get_stats(self) -> QueueState:
        """Haal queue statistieken op."""
        self._update_state()
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            return QueueState(**data)
        except (json.JSONDecodeError, TypeError, FileNotFoundError):
            return QueueState()

    def _update_state(self) -> None:
        """Update de queue state file."""
        done = self.list_done()
        failed = self.list_failed()
        pending_count = self.count_pending()

        issues_by_type = {}
        for r in done:
            # We can't easily extract issue_type from FixResult alone,
            # so we approximate from what we have
            pass

        state = QueueState(
            total_requests=pending_count + len(done) + len(failed),
            total_done=len(done),
            total_failed=len(failed),
            total_success=sum(1 for d in done if d.success),
            total_tokens=sum(d.tokens_used for d in done),
            avg_duration_ms=(
                sum(d.duration_ms for d in done) / max(1, len(done))
            ),
            last_activity=datetime.now().isoformat(),
            issues_fixed_by_type=issues_by_type,
        )
        self.state_file.write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def clear_queue(self) -> tuple[int, int, int]:
        """Maak de queue leeg. Returns (removed_pending, removed_done, removed_failed)."""
        counts = [0, 0, 0]
        for i, d in enumerate([self.pending_dir, self.done_dir, self.failed_dir]):
            for f in d.glob("*.json"):
                f.unlink()
                counts[i] += 1
        self._update_state()
        return tuple(counts)

    def learn_from_result(self, request_id: str, result: FixResult) -> dict:
        """Extraheer lessen uit een fix resultaat voor RSI memory."""
        return {
            "request_id": request_id,
            "issue_type": self._guess_issue_type(request_id),
            "success": result.success,
            "changes_made": result.changes_made,
            "error": result.error,
            "tokens_used": result.tokens_used,
        }

    def _guess_issue_type(self, request_id: str) -> str:
        """Probeer het issue type te raden uit pending/done files."""
        for d in [self.pending_dir, self.done_dir, self.failed_dir]:
            rf = d / f"{request_id}.json"
            if rf.exists():
                try:
                    data = json.loads(rf.read_text(encoding="utf-8"))
                    return data.get("issue_type", "unknown")
                except (json.JSONDecodeError, TypeError):
                    pass
        return "unknown"

    # ── Batch operaties ───────────────────────────────────────

    def submit_batch(self, requests_data: list[dict]) -> list[str]:
        """Submit meerdere fix-requests tegelijk. Returns list van IDs."""
        ids = []
        for req in requests_data:
            rid = self.submit_fix(
                file_path=req["file_path"],
                issue_type=req["issue_type"],
                description=req["description"],
                context=req.get("context", {}),
                priority=req.get("priority", 1.0),
            )
            if rid:
                ids.append(rid)
        return ids

    def wait_for_results(self, request_ids: list[str],
                         timeout_s: float = 300,
                         poll_interval_s: float = 2.0) -> dict[str, FixResult]:
        """Wacht tot alle requests verwerkt zijn (polling).

        In productie zou dit via een event systeem gaan, maar
        voor nu gebruiken we polling op de done/failed directories.
        """
        results = {}
        deadline = time.time() + timeout_s
        remaining = set(request_ids)

        while remaining and time.time() < deadline:
            for rid in list(remaining):
                result = self.get_result(rid)
                if result is not None:
                    results[rid] = result
                    remaining.discard(rid)
            if remaining:
                time.sleep(poll_interval_s)

        # Timeout: markeer overgebleven als pending
        for rid in remaining:
            results[rid] = FixResult(
                request_id=rid,
                success=False,
                error=f"Timeout na {timeout_s}s",
            )

        return results


# ── CLI ───────────────────────────────────────────────────────


def cmd_list_pending(bridge: LLMBridge, args) -> None:
    """CLI: Toon pending requests."""
    pending = bridge.list_pending()
    if not pending:
        print("✅ Geen pending fix-requests.")
        return

    print(f"\n{'='*70}")
    print(f"  ⏳ PENDING FIX-REQUESTS ({len(pending)})")
    print(f"{'='*70}")
    type_icons = {
        "docs": "📝", "types": "🏷️", "refactor": "🔧", "security": "🔒",
        "dead_code": "🗑️", "tests": "🧪", "complexity": "📊", "naming": "✏️",
        "imports": "📦", "error_handling": "🛡️", "performance": "⚡", "bugfix": "🐛",
    }
    for req in pending:
        icon = type_icons.get(req.issue_type, "❓")
        print(f"  [{req.id}] {icon} [{req.issue_type:15s}] {req.file_path}")
        print(f"         {req.description[:90]}")
    print()


def cmd_show(bridge: LLMBridge, args) -> None:
    """CLI: Toon details van een request."""
    req_id = args.id
    # Zoek in pending
    req_file = bridge.pending_dir / f"{req_id}.json"
    if not req_file.exists():
        # Zoek in done
        req_file = bridge.done_dir / f"{req_id}.json"
    if not req_file.exists():
        req_file = bridge.failed_dir / f"{req_id}.json"
    if not req_file.exists():
        print(f"❌ Request '{req_id}' niet gevonden.")
        return

    data = json.loads(req_file.read_text(encoding="utf-8"))
    print(f"\n{'='*70}")
    print(f"  Fix-Request: {data.get('id', '?')}")
    print(f"{'='*70}")
    print(f"  Status:     {data.get('status', '?')}")
    print(f"  Type:       {data.get('issue_type', '?')}")
    print(f"  Bestand:    {data.get('file_path', '?')}")
    print(f"  Tijd:       {data.get('timestamp', '?')}")
    print(f"  Prioriteit: {data.get('priority', 1.0)}")
    print(f"\n  Beschrijving:")
    print(f"  {data.get('description', '?')}")
    if data.get('context'):
        print(f"\n  Context:")
        ctx = data['context']
        for k, v in ctx.items():
            if isinstance(v, str) and len(v) > 100:
                v = v[:100] + "..."
            print(f"    {k}: {v}")
    if data.get('error'):
        print(f"\n  ❌ Error: {data['error']}")
    if data.get('changes_made'):
        print(f"\n  ✅ Changes: {data['changes_made']}")
    print()


def cmd_list_done(bridge: LLMBridge, args) -> None:
    """CLI: Toon afgewerkte resultaten."""
    done = bridge.list_done()
    failed = bridge.list_failed()
    if not done and not failed:
        print("Geen afgewerkte requests.")
        return

    all_results = [(r, "✅") for r in done] + [(r, "❌") for r in failed]
    print(f"\n{'='*70}")
    print(f"  AFGEWERKTE FIXES ({len(done)} ok, {len(failed)} gefaald)")
    print(f"{'='*70}")
    for result, icon in all_results:
        print(f"  {icon} [{result.request_id}] {result.file_path}")
        if result.success:
            print(f"     {result.changes_made[:100]}")
        else:
            print(f"     {result.error[:100]}")
    print()


def cmd_stats(bridge: LLMBridge, args) -> None:
    """CLI: Toon queue statistieken."""
    stats = bridge.get_stats()
    pending = bridge.count_pending()
    print(f"\n{'='*50}")
    print(f"  RSI FIX QUEUE STATS")
    print(f"{'='*50}")
    print(f"  Pending:  {pending}")
    print(f"  Done:     {stats.total_done} ({stats.total_success} success)")
    print(f"  Failed:   {stats.total_failed}")
    print(f"  Tokens:   {stats.total_tokens}")
    print(f"  Avg tijd: {stats.avg_duration_ms:.0f}ms")
    print(f"  Laatste:  {stats.last_activity[:19]}")
    print()


def cmd_mark_done(bridge: LLMBridge, args) -> None:
    """CLI: Markeer een request als done (handmatig)."""
    result = FixResult(
        request_id=args.id,
        timestamp=datetime.now().isoformat(),
        success=not args.failed,
        file_path=args.file or "",
        changes_made=args.message or "Handmatig afgewerkt",
    )
    bridge.mark_done(args.id, result)
    status = "✅" if result.success else "❌"
    print(f"  {status} Request {args.id} gemarkeerd als {'done' if result.success else 'failed'}.")


def cmd_clear(bridge: LLMBridge, args) -> None:
    """CLI: Maak de queue leeg."""
    p, d, f = bridge.clear_queue()
    print(f"  Queue geleegd: {p} pending, {d} done, {f} failed verwijderd.")


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="RSI LLM Bridge — Brug tussen RSI en Hermes voor code fixes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--workspace", "-w", default=".",
                        help="ToolCase workspace directory")

    sub = parser.add_subparsers(dest="command", help="Commando's")

    sub.add_parser("list-pending", help="Toon pending fix-requests")
    sub.add_parser("list-done", help="Toon afgewerkte fixes")
    sub.add_parser("stats", help="Toon queue statistieken")
    sub.add_parser("clear", help="Maak de queue leeg")

    show_p = sub.add_parser("show", help="Toon details van een request")
    show_p.add_argument("id", help="Request ID")

    mark_p = sub.add_parser("mark-done", help="Markeer request als done/failed")
    mark_p.add_argument("id", help="Request ID")
    mark_p.add_argument("--file", help="Bestandspad")
    mark_p.add_argument("--message", help="Beschrijving van de fix")
    mark_p.add_argument("--failed", action="store_true", help="Markeer als gefaald")

    parser.add_argument("--version", action="version",
                        version=f"rsi_llm_bridge.py v{__version__}")

    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    bridge = LLMBridge(workspace)

    commands = {
        "list-pending": cmd_list_pending,
        "list-done": cmd_list_done,
        "stats": cmd_stats,
        "show": cmd_show,
        "mark-done": cmd_mark_done,
        "clear": cmd_clear,
    }

    if args.command in commands:
        commands[args.command](bridge, args)
    else:
        # Default: toon pending + stats
        cmd_list_pending(bridge, args)
        cmd_stats(bridge, args)


if __name__ == "__main__":
    main()
