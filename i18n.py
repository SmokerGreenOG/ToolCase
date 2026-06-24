#!/usr/bin/env python3
"""
i18n.py — Central translation module for ToolCase v5.4.0.

Provides gettext-like functionality for English, Dutch, and German.

Usage:
    from i18n import t
    print(t("tool_not_found", lang="nl"))  # "❌ {target} bestaat niet"

Language codes: "en" (default), "nl" (Nederlands), "de" (Deutsch)
Can be set via LANG env var: LANG=nl python improve.py ...
"""

from __future__ import annotations

__maker__ = "SmokerGreenOG"

import _protect
import os
import sys

# ── Detect language ─────────────────────────────────────
_DEFAULT_LANG = os.environ.get("LANG", "en")[:2].lower()
if _DEFAULT_LANG not in ("en", "nl", "de"):
    _DEFAULT_LANG = "en"


# ── Translation table ───────────────────────────────────
# Keys: lowercase, underscore-separated identifiers
# Values: { "en": ..., "nl": ..., "de": ... }

TRANS = {
    # ── Generic UI ──
    "version": {
        "en": "v{VERSION}",
        "nl": "v{VERSION}",
        "de": "v{VERSION}",
    },
    "toolcase_title": {
        "en": "⚡ ToolCase v{VERSION} — All {COUNT} tools",
        "nl": "⚡ TOOLCASE v{VERSION} — Alle {COUNT} tools",
        "de": "⚡ TOOLCASE v{VERSION} — Alle {COUNT} Werkzeuge",
    },
    "maker": {
        "en": "Maker",
        "nl": "Maker",
        "de": "Ersteller",
    },
    "safety_rules_label": {
        "en": "Safety rules",
        "nl": "Veiligheidsregels",
        "de": "Sicherheitsregeln",
    },
    "ignored_dirs_label": {
        "en": "Ignored directories",
        "nl": "Genegeerde directories",
        "de": "Ignorierte Verzeichnisse",
    },
    "total_tools": {
        "en": "Total tools",
        "nl": "Totaal tools",
        "de": "Werkzeuge insgesamt",
    },
    "core_tools": {
        "en": "Core",
        "nl": "Core",
        "de": "Kern",
    },
    "readonly_tools": {
        "en": "Read-only",
        "nl": "Read-only",
        "de": "Schreibgeschützt",
    },
    "needs_approval": {
        "en": "Needs Approval",
        "nl": "Goedkeuring nodig",
        "de": "Genehmigung nötig",
    },
    "high_risk": {
        "en": "High Risk",
        "nl": "Hoog Risico",
        "de": "Hohes Risiko",
    },
    "categories": {
        "en": "Categories",
        "nl": "Categorieën",
        "de": "Kategorien",
    },
    "tools_visible": {
        "en": "{n} tools visible",
        "nl": "{n} tools zichtbaar",
        "de": "{n} Werkzeuge sichtbar",
    },
    "no_tools_found": {
        "en": "No tools found matching your filters.",
        "nl": "Geen tools gevonden die voldoen aan de filters.",
        "de": "Keine Werkzeuge gefunden, die Ihren Filtern entsprechen.",
    },
    "try_different_filters": {
        "en": "Try different filters or reset.",
        "nl": "Probeer andere filters of reset.",
        "de": "Versuchen Sie andere Filter oder setzen Sie zurück.",
    },
    "could_not_load_config": {
        "en": "Could not load tools_config.json.",
        "nl": "Kon tools_config.json niet laden.",
        "de": "Konnte tools_config.json nicht laden.",
    },

    # ── improve.py output ──
    "code_improvement_tool": {
        "en": "🔍 Code Improvement Tool v{VERSION}",
        "nl": "🔍 Code Improvement Tool v{VERSION}",
        "de": "🔍 Code Improvement Tool v{VERSION}",
    },
    "hermes_hint": {
        "en": "💡 HERMES: Use me to improve code!",
        "nl": "💡 HERMES: Gebruik mij om code te verbeteren!",
        "de": "💡 HERMES: Verwende mich, um Code zu verbessern!",
    },
    "workflow_title": {
        "en": ("This is the Code Improvement Tool (v{VERSION}). Hermes can use this script\nto"
               "automatically analyze and improve code."),
        "nl": ("Dit is de Code Improvement Tool (v{VERSION}). Hermes kan dit script gebruiken\nom code"
               "automatisch te analyseren en te verbeteren."),
        "de": ("Dies ist das Code Improvement Tool (v{VERSION}). Hermes kann dieses Skript\nverwenden, um"
               "Code automatisch zu analysieren und zu verbessern."),
    },
    "workflow_step1": {
        "en": "  1. Analyze:  python improve.py <file>        (shows issues)",
        "nl": "  1. Analyseer:  python improve.py <bestand>        (toont issues)",
        "de": "  1. Analysieren:  python improve.py <datei>        (zeigt Probleme)",
    },
    "workflow_step2": {
        "en": "  2. Auto-fix: python improve.py <file> -f     (auto fix)",
        "nl": "  2. Fix syntax: python improve.py <bestand> -f     (automatisch fixen)",
        "de": ("  2. Automatisch korrigieren: python improve.py <datei> -f     (automatisch"
               "korrigieren)"),
    },
    "workflow_step3": {
        "en": "  3. List tools: python improve.py --list-tools  (show all 60 tools)",
        "nl": "  3. python improve.py --list-tools              (toon alle 60 tools)",
        "de": "  3. python improve.py --list-tools              (alle 60 Werkzeuge anzeigen)",
    },
    "workflow_loop_hint": {
        "en": ("The 'toolcase-self-improve' skill contains the full"
               " workflow\nfor Hermes to independently improve code."),
        "nl": ("De 'toolcase-self-improve' skill bevat de volledige"
               " workflow\nvoor Hermes om zelfstandig code te verbeteren."),
        "de": ("Die 'toolcase-self-improve' Skill enthält den vollständigen"
               " Workflow\nfür Hermes, um Code eigenständig zu verbessern."),
    },
    "workflow_self_hint": {
        "en": ("Tip: Hermes can improve THIS file by loading it\nwith read_file, analyzing with"
               "improve.py, and fixing with patch."),
        "nl": ("Tip: Hermes kan DIT BESTAND zelf verbeteren door het te laden\nmet read_file, te"
               "analyseren met improve.py, en te fixen met patch."),
        "de": ("Tipp: Hermes kann DIESE DATEI selbst verbessern, indem er sie\nmit read_file lädt, mit"
               "improve.py analysiert und mit patch korrigiert."),
    },

    # ── File analysis ──
    "file_report": {
        "en": "📄 {file}",
        "nl": "📄 {file}",
        "de": "📄 {file}",
    },
    "lines_count": {
        "en": "📊 {n} lines",
        "nl": "📊 {n} regels",
        "de": "📊 {n} Zeilen",
    },
    "syntax_ok": {
        "en": "✅ Syntax OK",
        "nl": "✅ Syntax OK",
        "de": "✅ Syntax OK",
    },
    "syntax_fail": {
        "en": "❌ Syntax: {msg}",
        "nl": "❌ Syntax: {msg}",
        "de": "❌ Syntax: {msg}",
    },
    "issues_found": {
        "en": "⚠  Issues ({n}):",
        "nl": "⚠  Issues ({n}):",
        "de": "⚠  Probleme ({n}):",
    },
    "longest_lines": {
        "en": "📏 Longest lines:",
        "nl": "📏 Langste regels:",
        "de": "📏 Längste Zeilen:",
    },
    "looks_good": {
        "en": "✨ Looks good!",
        "nl": "✨ Ziet er goed uit!",
        "de": "✨ Sieht gut aus!",
    },
    "file_not_found": {
        "en": "❌ {target} does not exist",
        "nl": "❌ {target} bestaat niet",
        "de": "❌ {target} existiert nicht",
    },
    "not_python_file": {
        "en": "⚠  {target} is not a Python file (.py)",
        "nl": "⚠  {target} is geen Python-bestand (.py)",
        "de": "⚠  {target} ist keine Python-Datei (.py)",
    },
    "no_python_files": {
        "en": "No Python files found in {target}",
        "nl": "Geen Python-bestanden gevonden in {target}",
        "de": "Keine Python-Dateien in {target} gefunden",
    },
    "files_found": {
        "en": "📁 {n} file(s) found in {target}",
        "nl": "📁 {n} bestand(en) gevonden in {target}",
        "de": "📁 {n} Datei(en) in {target} gefunden",
    },
    "files_scanned": {
        "en": "📁 {n} file(s) scanned",
        "nl": "📁 {n} bestand(en) gescand",
        "de": "📁 {n} Datei(en) gescannt",
    },
    "summary_title": {
        "en": "📊 SUMMARY",
        "nl": "📊 SAMENVATTING",
        "de": "📊 ZUSAMMENFASSUNG",
    },
    "syntax_all_ok": {
        "en": "✅ All OK",
        "nl": "✅ Allemaal",
        "de": "✅ Alle OK",
    },
    "syntax_some_fail": {
        "en": "❌ Some have errors",
        "nl": "❌ Sommige hebben fouten",
        "de": "❌ Einige haben Fehler",
    },
    "issues_total": {
        "en": "Issues:    {n}",
        "nl": "Issues:    {n}",
        "de": "Probleme:  {n}",
    },
    "loop_hint_summary": {
        "en": "💡 Hermes can tackle these issues via the toolcase-self-improve skill.",
        "nl": "💡 Hermes kan deze issues aanpakken via de toolcase-self-improve skill.",
        "de": "💡 Hermes kann diese Probleme mit der toolcase-self-improve Skill beheben.",
    },
    "backup_failed": {
        "en": "⚠  Backup failed: {e}",
        "nl": "⚠  Backup mislukt: {e}",
        "de": "⚠  Backup fehlgeschlagen: {e}",
    },

    # ── Tool runner ──
    "running_tool": {
        "en": "🛠  {name} — {target}",
        "nl": "🛠  {name} — {target}",
        "de": "🛠  {name} — {target}",
    },
    "exit_code": {
        "en": "⚠  Exit code: {code}",
        "nl": "⚠  Exit code: {code}",
        "de": "⚠  Exit-Code: {code}",
    },
    "auto_fix_mode": {
        "en": ("🔧 Auto-fix mode — attempting syntax repair...\n   (Hermes can do this via the"
               "toolcase-self-improve skill)"),
        "nl": ("🔧 Auto-fix modus — probeer syntax te repareren...\n   (Hermes kan dit via de"
               "toolcase-self-improve skill)"),
        "de": ("🔧 Auto-Fix-Modus — versuche Syntax-Reparatur...\n   (Hermes kann dies mit der"
               "toolcase-self-improve Skill tun)"),
    },

    # ── Language names ──
    "lang_en": {"en": "English", "nl": "Engels", "de": "Englisch"},
    "lang_nl": {"en": "Dutch", "nl": "Nederlands", "de": "Niederländisch"},
    "lang_de": {"en": "German", "nl": "Duits", "de": "Deutsch"},
    "language_label": {
        "en": "Language: {lang}",
        "nl": "Taal: {lang}",
        "de": "Sprache: {lang}",
    },
    "lang_flag": {
        "en": "🇬🇧",
        "nl": "🇳🇱",
        "de": "🇩🇪",
    },

    # ── Dashboard ──
    "dashboard_title": {
        "en": "ToolCase Dashboard",
        "nl": "ToolCase Dashboard",
        "de": "ToolCase Dashboard",
    },
    "dashboard_subtitle": {
        "en": "Code Improvement Toolkit · SmokerGreenOG · v{VERSION}",
        "nl": "Code Improvement Toolkit · SmokerGreenOG · v{VERSION}",
        "de": "Code Improvement Toolkit · SmokerGreenOG · v{VERSION}",
    },
    "expand_all": {
        "en": "📂 Expand All",
        "nl": "📂 Uitklappen",
        "de": "📂 Alle ausklappen",
    },
    "collapse_all": {
        "en": "📁 Collapse All",
        "nl": "📁 Inklappen",
        "de": "📁 Alle einklappen",
    },
    "reset": {
        "en": "🔄 Reset",
        "nl": "🔄 Reset",
        "de": "🔄 Zurücksetzen",
    },
    "search_placeholder": {
        "en": "🔍 Search by tool name, tag or description...",
        "nl": "🔍 Zoek op toolnaam, tag of beschrijving...",
        "de": "🔍 Suche nach Werkzeugnamen, Tags oder Beschreibung...",
    },
    "all_categories": {
        "en": "All categories",
        "nl": "Alle categorieën",
        "de": "Alle Kategorien",
    },
    "all_risks": {
        "en": "All risks",
        "nl": "Alle risico's",
        "de": "Alle Risiken",
    },
    "all_tags": {
        "en": "All tags",
        "nl": "Alle tags",
        "de": "Alle Tags",
    },
    "safety_rules_heading": {
        "en": "🔒 Safety Rules",
        "nl": "🔒 Veiligheidsregels",
        "de": "🔒 Sicherheitsregeln",
    },
    "tool_type": {
        "en": "Type",
        "nl": "Type",
        "de": "Typ",
    },
    "tool_risk": {
        "en": "Risk",
        "nl": "Risk",
        "de": "Risiko",
    },
    "tool_tags": {
        "en": "Tags",
        "nl": "Tags",
        "de": "Tags",
    },
    "tool_description": {
        "en": "What it does",
        "nl": "Wat het doet",
        "de": "Was es tut",
    },
    "search_no_results": {
        "en": "🔍 No tools found.",
        "nl": "🔍 Geen tools gevonden.",
        "de": "🔍 Keine Werkzeuge gefunden.",
    },
}


def t(key: str, lang: str | None = None, **kwargs) -> str:
    """
    Translate a key into the target language.

    Args:
        key: Translation key (lowercase, underscore-separated)
        lang: Language code ("en", "nl", "de"). Defaults to env LANG or "en".
        **kwargs: Format variables (e.g. n=5, target="foo.py")

    Returns:
        Translated and formatted string. Falls back to 'en' if key or lang missing.
    """
    if lang is None:
        lang = _DEFAULT_LANG
    entry = TRANS.get(key)
    if entry is None:
        return f"??{key}??"
    text = entry.get(lang) or entry.get("en", f"??{key}:{lang}??")
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text


def get_lang() -> str:
    """Return the active language code."""
    return _DEFAULT_LANG


def add_lang_arg(parser: argparse.ArgumentParser) -> None:
    """Add a --lang argument to an argparse parser."""
    parser.add_argument(
        "--lang", choices=["en", "nl", "de"], default=_DEFAULT_LANG,
        help="Output language: en (English), nl (Nederlands), de (Deutsch)"
    )


# ── Expose as module-level callable ─────────────────────
if __name__ == "__main__":
    # Quick test
    for lang in ("en", "nl", "de"):
        print(f"\n=== {lang.upper()} ===")
        print(t("dashboard_title", lang=lang))
        print(t("search_placeholder", lang=lang))
        print(t("file_not_found", lang=lang, target="test.py"))
        print(t("issues_found", lang=lang, n=5))
