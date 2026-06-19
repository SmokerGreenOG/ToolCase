# ⚡ ToolCase v3.0 — AI Agent Code Toolkit

[![Version](https://img.shields.io/badge/version-3.0.0-7C3AED?style=flat-square)]()
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)]()
[![License](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)]()
[![Hermes](https://img.shields.io/badge/hermes--agent-ready-06b6d4?style=flat-square)]()
[![Tests](https://img.shields.io/badge/tests-53%2F53-success?style=flat-square)]()
[![GitHub](https://img.shields.io/badge/github-SmokerGreenOG%2FToolCase-181717?style=flat-square&logo=github)]()

> **43 tools · 8 categories · 10 safety rules · 3 languages (EN/NL/DE)**  
> Built with ❤️ by [SmokerGreenOG](https://github.com/SmokerGreenOG)  \
> [![GitHub](https://img.shields.io/badge/Repo-SmokerGreenOG%2FToolCase-7C3AED?style=flat-square)](https://github.com/SmokerGreenOG/ToolCase)

---

# 🇬🇧 English

## 🚀 What is ToolCase?

**ToolCase** is a portable, production-ready code improvement toolkit designed for **AI agents** (Hermes, Claude Code, Codex, etc.) and **developers** alike.

It gives you **35 standalone tools** across 8 categories — from static analysis and security scanning to build diagnostics, release packaging, and an autonomous self-improvement loop.

**Zero external dependencies.** Runs on Windows, macOS, and Linux.

---

## 🖥️ Quick Start

```bash
# 1. Browse all 43 tools
python improve.py --list-tools

# 2. Scan a file for issues
python improve.py my_script.py

# 3. Security audit
python security_scan.py .

# 4. Full project health check
python project_doctor.py .

# 5. Autonomous self-improvement (dry-run mode)
python self_improve_loop.py --dry-run
```

---

## 🌐 Visual Dashboard

```bash
python -m http.server 8080 --directory .
# → http://localhost:8080/dashboard.html
```

The dashboard features:
- 📊 All 43 tools with risk levels, tags, and descriptions
- 🔍 Search by tool name, tag, or description
- 🏷️ Filter by category, risk level, or tag
- 🌍 Language toggle: **🇬🇧 English · 🇳🇱 Nederlands · 🇩🇪 Deutsch**
- 🎨 Dark purple/neon UI

---

## 📦 Installation for Hermes Users

Hermes Agent users get the full experience:

**Option A: Run the installer (Windows)**
```bash
.\install_toolcase.bat
```

**Option B: Manual skill install (any OS)**
```bash
mkdir -p ~/.hermes/skills/toolcase-self-improve
cp SKILL.md ~/.hermes/skills/toolcase-self-improve/
cp manifest.json ~/.hermes/skills/toolcase-self-improve/

# Then use it in any Hermes session
hermes -s toolcase-self-improve
```

---

## 🌍 Internationalization

All tools support 3 languages:

```bash
# English (default)
python improve.py --list-tools --lang en

# Nederlands
python improve.py --list-tools --lang nl

# Deutsch
python improve.py --list-tools --lang de
```

---

## 🔒 Safety Rules (10 hard rules)

| # | Rule |
|---|------|
| 1 | No destructive action without a backup |
| 2 | No terminal command without `command_guard.py` |
| 3 | No changes to .env, package.json, or config without `file_guard.py` |
| 4 | No patch without `patch_preview.py` first |
| 5 | No release if `security_scan.py` finds API keys |
| 6 | No release if `build_doctor.py` fails |
| 7 | No restore without explicit confirmation |
| 8 | No writing outside the workspace |
| 9 | No deletion without approval |
| 10 | No hidden changes — always show the diff |

---

## ⚙️ Requirements

- **Python 3.11+**
- That's it. Seriously. No pip installs. No npm packages.

> Some tools (test_runner, build_doctor) will detect and use **pytest**, **vitest**, **cargo**, etc. if installed in the target project — but ToolCase itself has **zero external dependencies**.

---

# 🇩🇪 Deutsch

## 🚀 Was ist ToolCase?

**ToolCase** ist ein portables, produktionsreifes Code-Verbesserungs-Toolkit für **KI-Agenten** (Hermes, Claude Code, Codex usw.) und **Entwickler**.

Es bietet **35 eigenständige Werkzeuge** in 8 Kategorien — von statischer Analyse und Sicherheitsscans bis hin zu Build-Diagnostik, Release-Packaging und einer autonomen Selbstverbesserungs-Schleife.

**Keine externen Abhängigkeiten.** Läuft auf Windows, macOS und Linux.

---

## 🖥️ Schnellstart

```bash
# 1. Alle 35 Werkzeuge anzeigen
python improve.py --list-tools

# 2. Eine Datei auf Probleme prüfen
python improve.py meine_datei.py

# 3. Sicherheitsaudit
python security_scan.py .

# 4. Vollständiger Projekt-Check
python project_doctor.py .

# 5. Autonome Selbstverbesserung (Trockenlauf)
python self_improve_loop.py --dry-run
```

---

## 🌐 Dashboard (visuelle Oberfläche)

```bash
python -m http.server 8080 --directory .
# → http://localhost:8080/dashboard.html
```

Das Dashboard bietet:
- 📊 Alle 35 Werkzeuge mit Risikostufen, Tags und Beschreibungen
- 🔍 Suche nach Name, Tag oder Beschreibung
- 🏷️ Filter nach Kategorie, Risikostufe oder Tag
- 🌍 Sprachumschaltung: **🇬🇧 English · 🇳🇱 Nederlands · 🇩🇪 Deutsch**
- 🎨 Dunkles Purple/Neon-Design

---

## 📦 Installation für Hermes-Benutzer

Hermes-Agent-Benutzer erhalten das volle Erlebnis:

**Option A: Installationsskript ausführen (Windows)**
```bash
.\install_toolcase.bat
```

**Option B: Manuelle Skill-Installation (beliebiges OS)**
```bash
mkdir -p ~/.hermes/skills/toolcase-self-improve
cp SKILL.md ~/.hermes/skills/toolcase-self-improve/
cp manifest.json ~/.hermes/skills/toolcase-self-improve/

# Dann in jeder Hermes-Sitzung verwenden
hermes -s toolcase-self-improve
```

---

## 🌍 Mehrsprachigkeit

Alle Werkzeuge unterstützen 3 Sprachen:

```bash
# English (Standard)
python improve.py --list-tools --lang en

# Nederlands
python improve.py --list-tools --lang nl

# Deutsch
python improve.py --list-tools --lang de
```

---

## 🔒 Sicherheitsregeln (10 harte Regeln)

| # | Regel |
|---|-------|
| 1 | Keine zerstörerische Aktion ohne Backup |
| 2 | Kein Terminal-Befehl ohne `command_guard.py` |
| 3 | Keine Änderungen an .env, package.json oder Config ohne `file_guard.py` |
| 4 | Kein Patch ohne vorheriges `patch_preview.py` |
| 5 | Kein Release, wenn `security_scan.py` API-Keys findet |
| 6 | Kein Release, wenn `build_doctor.py` fehlschlägt |
| 7 | Keine Wiederherstellung ohne explizite Bestätigung |
| 8 | Kein Schreiben außerhalb des Arbeitsbereichs |
| 9 | Kein Löschen ohne Genehmigung |
| 10 | Keine versteckten Änderungen — immer den Diff anzeigen |

---

## ⚙️ Systemvoraussetzungen

- **Python 3.11+**
- Das war's. Ernsthaft. Kein pip install. Keine npm-Pakete.

> Einige Werkzeuge (test_runner, build_doctor) erkennen und nutzen **pytest**, **vitest**, **cargo** usw., falls im Zielprojekt installiert — aber ToolCase selbst hat **keine externen Abhängigkeiten**.

---

# 🧰 Tool-Übersicht / Tool Reference

## 🔍 Analyse & Code-Qualität (6)

| # | Werkzeug | EN: What it does / DE: Beschreibung |
|---|----------|--------------------------------------|
| 1 | `improve.py` | Syntax check + lint (lange Zeilen, Leerzeichen, TODO/FIXME) |
| 2 | `multiscan.py` | Mehrsprachen-Scanner — Python, TypeScript, TSX, Rust |
| 3 | `complexity.py` | Zyklomatische Komplexität & kognitive Last messen |
| 4 | `depgraph.py` | Import/Export-Abhängigkeitsgraph + zirkuläre Abhängigkeiten |
| 5 | `patch_preview.py` | Diff-Vorschau vor dem Anwenden eines Patches |
| 6 | `dead_code_finder.py` | Unbenutzte Imports, tote Funktionen, auskommentierter Code |

## 🛡️ Sicherheit & Umgebung (4)

| # | Werkzeug | Beschreibung |
|---|----------|--------------|
| 7 | `security_scan.py` | Hardcodierte API-Keys, Tokens, Passwörter, eval/exec, SQL/Shell-Injection |
| 8 | `env_check.py` | .env-Validierung, fehlende Variablen, .env.example automatisch generieren |
| 9 | `dependency_audit.py` | Python/Node/Rust-Abhängigkeitsaudit — Schwachstellen, unpinned Versions |
| 22 | `permission_audit.py` | Agent-Berechtigungsaudit — Lesen, Schreiben, Terminal, Internet usw. |

## 🩺 Projekt-Gesundheit & Diagnostik (6)

| # | Werkzeug | Beschreibung |
|---|----------|--------------|
| 10 | `project_doctor.py` | Projektstruktur, `__init__.py`, Git-Status, Namenskonventionen |
| 11 | `workspace_indexer.py` | Workspace-Index nach Sprache, Duplikaterkennung, Glob-Suche |
| 12 | `test_runner.py` | Tests finden & ausführen — pytest, vitest, jest, cargo |
| 13 | `agent_memory.py` | Hermes-Agent-Zustand anzeigen — Config, Skills, Plugins, Memory, Cron |
| 28 | `log_viewer.py` | Logdateien finden, Fehler sprachübergreifend zusammenfassen |
| 29 | `error_explainer.py` | Fehler/Traceback → verständliche Erklärung + Lösung (30+ Muster) |

## 🎨 Frontend/Backend & UI (8)

| # | Werkzeug | Beschreibung |
|---|----------|--------------|
| 14 | `route_scanner.py` | Frontend-Routen-Scanner, Erkennung verwaister Seiten |
| 15 | `frontend_backend_linker.py` | API-Aufrufe mit Backend-Endpunkten abgleichen |
| 23 | `api_contract_checker.py` | Erkennung von Pfad/Methode/Request/Response-Konflikten |
| 16 | `ui_consistency.py` | CSS-Variablen vs. hardcodierte Hex-Werte, Namenskonventionen |
| 17 | `feature_gap_analyzer.py` | Fehlende Fehlerbehandlung, Ladezustände, Validierung |
| 25 | `button_action_scanner.py` | Buttons/Formulare/Menüs ohne echte Aktionen |
| 26 | `state_inspector.py` | React/Vue/Svelte-State-Analyse — ungenutzter State, fehlendes Loading/Error |
| 24 | `fake_ui_detector.py` | Demo/Fake-UI-Erkennung — Mock-Daten, Platzhalter-Routen, Dummy-Handler |

## 🔒 Agenten-Sicherheit (5)

| # | Werkzeug | Beschreibung |
|---|----------|--------------|
| 20 | `command_guard.py` | Terminal-Befehlssicherheit — blockiert `rm -rf`, `curl|sh`, gefährliches chmod |
| 21 | `file_guard.py` | Schützt .env, package.json, Config-Dateien vor Überschreiben |
| 22 | `permission_audit.py` | Agent-Berechtigungsaudit (auch unter Sicherheit) |
| 5 | `patch_preview.py` | Diff-Vorschau vor Patches (auch unter Analyse) |
| 32 | `backup_manager.py` | Zeitgestempelte Snapshots, Wiederherstellung, Diff-Ansicht, Auto-Bereinigung |

## 🔄 Lebenszyklus & Wiederherstellung (4)

| # | Werkzeug | Beschreibung |
|---|----------|--------------|
| 18 | `rollback.py` | `.bak`-Backup-Wiederherstellung |
| 19 | `todo_tracker.py` | TODO/FIXME/HACK/XXX/BUG-Markierungen scannen |
| 32 | `backup_manager.py` | Snapshots & Backup-Verwaltung |
| 33 | `docs_sync.py` | README/Dokumentation mit aktuellem Code abgleichen |

## 📦 Build, Test & Release (5)

| # | Werkzeug | Beschreibung |
|---|----------|--------------|
| 27 | `build_doctor.py` | Build-Diagnostik — npm, vite, tsc, Python-Imports |
| 12 | `test_runner.py` | Multi-Framework-Testausführung |
| 30 | `release_packager.py` | Preflight-Prüfungen → Build → ZIP → Changelog — komplette Release-Pipeline |
| 31 | `changelog_generator.py` | CHANGELOG.md aus Git-Log oder Patch-Verlauf generieren |
| 9 | `dependency_audit.py` | Abhängigkeits-Schwachstellenaudit (auch unter Sicherheit) |

## 🧠 Skills & Memory (3)

| # | Werkzeug | Beschreibung |
|---|----------|--------------|
| 13 | `agent_memory.py` | Hermes-Agent-Zustandsanzeige (auch unter Projekt-Gesundheit) |
| 34 | `skill_installer.py` | Hermes/Sabine-Skill-Installer & -Validator |
| 11 | `workspace_indexer.py` | Workspace-Index (auch unter Projekt-Gesundheit) |

## 🔄 Selbstverbesserungs-Schleife

| # | Werkzeug | Beschreibung |
|---|----------|--------------|
| 35 | `self_improve_loop.py` | 13-stufige autonome Verbesserungsschleife — scannen, planen, anwenden, verifizieren |

---

## 🧪 Selbstverbesserungs-Schleife / Self-Improvement Loop

Das Herzstück — `self_improve_loop.py` ist ein vollautonomer 13-stufiger Workflow:

```
▶ Scan → Plan → Backup → Patch → Verify → Commit → Test → Repeat
```

```bash
# Dry run / Trockenlauf (sichere Vorschau)
python self_improve_loop.py --dry-run

# Apply 3 improvement cycles / 3 Verbesserungszyklen anwenden
python self_improve_loop.py --cycles 3
```

Folgt denselben 10 Sicherheitsregeln und ändert nie Dateien ohne vorheriges Backup.

---

## 📁 Projektstruktur / Project Structure

```
ToolCase v3.0/
├── improve.py                 # Main dispatcher — alle 35 Werkzeuge
├── tools_config.json          # Zentrale JSON-Konfiguration
├── manifest.json              # Hermes-Skill-Manifest
├── dashboard.html             # Visuelles Dashboard (im Browser öffnen)
├── SKILL.md                   # Hermes-Agent-Skill-Definition
├── i18n.py                    # Internationalisierung (EN/NL/DE)
├── _protect.py                # Maker-Signaturschutz
├── install_toolcase.bat       # Windows-Installer
├── icon.png                   # ToolCase-Logo
├── LICENSE                    # MIT
├── *.py                       # 35 eigenständige Werkzeug-Skripte
├── demo/
│   └── quickserve.py          # Schneller Demo-HTTP-Server
└── README.md                  # ← Du liest mich gerade
```

---

## 📊 Dashboard-Kennzahlen / Metrics

| Metrik / Metric | Wert / Value |
|-----------------|--------------|
| Werkzeuge / Tools | 35 |
| Schreibgeschützt / Read-only | 24 |
| Benötigt Genehmigung / Needs approval | 9 |
| Hohes Risiko / High risk | 3 |
| Mittleres Risiko / Medium risk | 4 |
| Niedriges Risiko / Low risk | 28 |
| Kategorien / Categories | 8 |
| Sprachen / Languages | 3 (EN/NL/DE) |

---

## 📝 Lizenz / License

MIT License — siehe [LICENSE](LICENSE).

**Maker / Ersteller:** [SmokerGreenOG](https://github.com/SmokerGreenOG)  
**Version:** 3.0.0  
**Gebaut für / Built for:** Hermes Agent · Claude Code · Codex · Jeder KI-Agent

---

> ⚡ *"Your code's best friend — whether human or AI."*  
> *"Der beste Freund deines Codes — ob Mensch oder KI."*
