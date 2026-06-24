#!/usr/bin/env python3
"""rsi_apply_docs.py — Batch docstring applicator voor RSI LLM queue.

Leest pending docstring requests uit de LLM bridge, voegt ontbrekende
docstrings toe aan Python functies, en markeert de resultaten.

Gebruik:
    python rsi_apply_docs.py           # Verwerk alle pending doc-requests
    python rsi_apply_docs.py --dry-run # Toon wat er zou gebeuren
    python rsi_apply_docs.py --id <id> # Verwerk specifieke request
"""

from __future__ import annotations

import _protect
import argparse
import ast
import json
import sys
from datetime import datetime
from pathlib import Path

# Import de bridge
try:
    from rsi_llm_bridge import LLMBridge, FixResult
except ImportError:
    print("❌ rsi_llm_bridge.py niet gevonden")
    sys.exit(1)

TOOLCASE_DIR = Path(__file__).parent.resolve()


def find_undocumented_functions(filepath: Path) -> list[dict]:
    """Vind functies die een docstring missen. Returns [{name, lineno, args}]."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(content)
    except (SyntaxError, Exception):
        return []

    undocumented = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Check of er een docstring is
            has_docstring = False
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                has_docstring = True

            if not has_docstring:
                # Skip dunder methods en hele korte functies
                if node.name.startswith('__') and node.name.endswith('__'):
                    continue
                # Skip inner/nested functions zonder echte body
                if not node.body:
                    continue

                args = [a.arg for a in node.args.args]
                undocumented.append({
                    "name": node.name,
                    "lineno": node.lineno,
                    "args": args,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                })

    return undocumented


def generate_docstring(func_name: str, args: list[str], is_async: bool = False) -> str:
    """Genereer een zinnige docstring op basis van de functienaam en arguments."""
    # Converteer snake_case naar leesbare tekst
    readable = func_name.replace('_', ' ')

    # Patterns voor bekende prefixes
    prefixes = {
        'get_': 'Get',
        'set_': 'Set',
        'find_': 'Find',
        'check_': 'Check',
        'is_': 'Check if',
        'has_': 'Check if',
        'can_': 'Check if',
        'should_': 'Check if',
        'load_': 'Load',
        'save_': 'Save',
        'read_': 'Read',
        'write_': 'Write',
        'parse_': 'Parse',
        'scan_': 'Scan',
        'run_': 'Run',
        'build_': 'Build',
        'create_': 'Create',
        'delete_': 'Delete',
        'update_': 'Update',
        'validate_': 'Validate',
        'format_': 'Format',
        'generate_': 'Generate',
        'compute_': 'Compute',
        'calculate_': 'Calculate',
        'fetch_': 'Fetch',
        'send_': 'Send',
        'apply_': 'Apply',
        'collect_': 'Collect',
        'detect_': 'Detect',
        'extract_': 'Extract',
        'convert_': 'Convert',
        'normalize_': 'Normalize',
        'resolve_': 'Resolve',
        'process_': 'Process',
        'handle_': 'Handle',
        'setup_': 'Set up',
        'init_': 'Initialize',
        'clean_': 'Clean',
        'merge_': 'Merge',
        'copy_': 'Copy',
        'move_': 'Move',
        'list_': 'List',
        'show_': 'Show',
        'print_': 'Print',
        'download_': 'Download',
        'upload_': 'Upload',
        'install_': 'Install',
        'uninstall_': 'Uninstall',
        'verify_': 'Verify',
        'ensure_': 'Ensure',
        'require_': 'Require',
        'register_': 'Register',
        'unregister_': 'Unregister',
    }

    action = f"{readable}."
    for prefix, replacement in prefixes.items():
        if func_name.startswith(prefix):
            rest = func_name[len(prefix):].replace('_', ' ')
            action = f"{replacement} {rest}."
            break

    # Args toevoegen
    arg_part = ""
    if args:
        arg_names = [a for a in args if a not in ('self', 'cls')]
        if arg_names:
            arg_part = f"\n\n    Args:\n        " + "\n        ".join(
                f"{a}: Description." for a in arg_names
            )
            arg_part += f"\n\n    Returns:\n        Description."

    async_prefix = " (async)" if is_async else ""
    return f'"""{action}{async_prefix}{arg_part}\n    """'


def apply_docstrings(filepath: Path, dry_run: bool = False) -> dict:
    """Voeg docstrings toe aan alle ongedocumenteerde functies in een bestand.

    Returns {"fixed": N, "errors": [...]}"""
    result = {"fixed": 0, "errors": [], "details": []}
    undocumented = find_undocumented_functions(filepath)

    if not undocumented:
        return result

    content = filepath.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    modified = list(lines)

    # Sort op lineno reversed (van onder naar boven om line numbers stabiel te houden)
    for func in sorted(undocumented, key=lambda f: f['lineno'], reverse=True):
        try:
            lineno = func['lineno'] - 1  # 0-indexed
            # Vind de functie definitie lijn
            if lineno >= len(modified):
                continue

            func_line = modified[lineno]
            # Bepaal indent van de functie
            indent = len(func_line) - len(func_line.lstrip())

            # De docstring moet na de functie-definitie komen
            # Maar voor de body (als er een body is)
            doc_indent = indent + 4  # Standaard 4-spaces indent
            docstring = generate_docstring(func['name'], func['args'], func['is_async'])
            doc_lines = [(" " * doc_indent) + line for line in docstring.split('\n')]

            # Bepaal of de functie een inline body heeft of multi-line
            if lineno + 1 < len(modified):
                next_line = modified[lineno + 1]
                next_indent = len(next_line) - len(next_line.lstrip()) if next_line.strip() else 99
                # Als de volgende regel meer geïndenteerd is dan de functie, 
                # voeg docstring toe vóór de body
                insert_at = lineno + 1
            else:
                insert_at = lineno + 1

            # Insert de docstring regels, plus een eventuele scheidingslijn
            for i, dline in enumerate(doc_lines):
                modified.insert(insert_at + i, dline)

            result["fixed"] += 1
            result["details"].append(f"  + {func['name']}() in {filepath.name}")

        except Exception as e:
            result["errors"].append(f"  ✗ {func['name']}: {e}")

    if result["fixed"] > 0 and not dry_run:
        new_content = "\n".join(modified)
        if not new_content.endswith("\n"):
            new_content += "\n"
        # Valideer syntax
        try:
            ast.parse(new_content)
        except SyntaxError as e:
            result["errors"].append(f"Syntax error: {e}")
            return result  # Don't write broken code

        filepath.write_text(new_content, encoding="utf-8")

    return result


def process_queue(dry_run: bool = False) -> dict:
    """Verwerk alle pending doc-requests in de LLM bridge queue."""
    bridge = LLMBridge(TOOLCASE_DIR)
    pending = bridge.list_pending()

    doc_requests = [r for r in pending if r.issue_type == "docs"]
    if not doc_requests:
        print("Geen doc-requests in queue.")
        return {"processed": 0, "total_fixed": 0, "failed": 0}

    print(f"\n{'='*60}")
    print(f"  📝 DOCSTRING BATCH FIXER")
    print(f"  {len(doc_requests)} doc-requests in queue")
    print(f"  {'='*60}")

    total_fixed = 0
    total_failed = 0
    processed = 0

    for req in doc_requests:
        filepath = Path(req.file_path)
        if not filepath.exists():
            print(f"  ⚠ {filepath.name}: Bestand niet gevonden")
            total_failed += 1
            # Markeer als failed in bridge
            result = FixResult(
                request_id=req.id,
                timestamp=datetime.now().isoformat(),
                success=False,
                file_path=str(filepath),
                error="Bestand niet gevonden",
            )
            bridge.mark_done(req.id, result)
            continue

        print(f"\n  📄 {filepath.name}")
        start_time = datetime.now()

        result = apply_docstrings(filepath, dry_run=dry_run)
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        for detail in result["details"]:
            print(detail)
        for error in result["errors"]:
            print(error)

        total_fixed += result["fixed"]
        processed += 1

        if result["fixed"] > 0 or not result["errors"]:
            # Success
            fix_result = FixResult(
                request_id=req.id,
                timestamp=datetime.now().isoformat(),
                success=True,
                file_path=str(filepath),
                changes_made=f"{result['fixed']} docstrings toegevoegd",
                diff_summary="\n".join(result["details"]),
                duration_ms=duration_ms,
            )
        else:
            total_failed += 1
            fix_result = FixResult(
                request_id=req.id,
                timestamp=datetime.now().isoformat(),
                success=False,
                file_path=str(filepath),
                error="\n".join(result["errors"]) if result["errors"] else "Geen fixes toegepast",
            )

        if not dry_run:
            bridge.mark_done(req.id, fix_result)

    summary = {
        "processed": processed,
        "total_fixed": total_fixed,
        "failed": total_failed,
    }

    print(f"\n  {'='*60}")
    print(f"  ✅ {total_fixed} docstrings toegevoegd in {processed} bestanden")
    print(f"  ❌ {total_failed} gefaald")
    print(f"  {'='*60}")

    return summary


def main() -> None:
    """main.
        """
    parser = argparse.ArgumentParser(
        description="Batch docstring applicator voor RSI LLM queue",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Toon wat er zou gebeuren zonder te schrijven")
    parser.add_argument("--id", help="Verwerk alleen deze request ID")
    parser.add_argument("--version", action="version", version="rsi_apply_docs v1.0.0")

    args = parser.parse_args()

    if args.id:
        bridge = LLMBridge(TOOLCASE_DIR)
        # Find the request
        req_file = bridge.pending_dir / f"{args.id}.json"
        if not req_file.exists():
            print(f"❌ Request {args.id} niet gevonden.")
            sys.exit(1)
        data = json.loads(req_file.read_text(encoding="utf-8"))
        filepath = Path(data["file_path"])
        result = apply_docstrings(filepath, dry_run=args.dry_run)
        for d in result["details"]:
            print(d)
        print(f"\n{result['fixed']} docstrings toegevoegd.")
    else:
        process_queue(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
