#!/usr/bin/env python3
"""rsi_report_html.py — Dark-themed HTML report generator voor RSI v2.0.

Genereert een interactief HTML rapport van RSI cycli met Chart.js grafieken,
stat cards, severity dots en cross-file analyse — in ToolCase's signature
dark neon stijl (#120720 bg, purple/pink/blue/cyan accenten).

Gebruik:
    python rsi_report_html.py                           # Genereer uit laatste RSI data
    python rsi_report_html.py --input report.json       # Specifiek JSON rapport
    python rsi_report_html.py --output dashboard.html   # Custom output path
    python rsi_report_html.py --open                    # Open in browser na generatie
"""

from __future__ import annotations

__maker__ = "SmokerGreenOG"
__version__ = "1.0.0"

import _protect
import argparse
import json
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

TOOLCASE_DIR = Path(__file__).parent.resolve()
DEFAULT_INPUT = TOOLCASE_DIR / ".rsi_reports"
DEFAULT_OUTPUT = TOOLCASE_DIR / "rsi_dashboard.html"


def _find_latest_report() -> Optional[Path]:
    """Vind het meest recente RSI rapport."""
    if not DEFAULT_INPUT.exists():
        return None
    reports = sorted(DEFAULT_INPUT.glob("rsi_report_*.json"), reverse=True)
    return reports[0] if reports else None


def _load_json(path: Path) -> dict:
    """Laad en parse een JSON bestand — met of zonder BOM."""
    raw = path.read_text(encoding="utf-8-sig")
    return json.loads(raw)


def _load_metrics(workspace: Path) -> dict:
    """Laad de actuele metrics uit de RSI memory."""
    memory_file = workspace / ".rsi_memory.json"
    if memory_file.exists():
        try:
            return json.loads(memory_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def generate_html(report_data: list[dict], memory_data: dict = None,
                  output_path: Path = DEFAULT_OUTPUT) -> str:
    """Genereer een compleet HTML rapport."""

    memory_data = memory_data or {}

    # ── Verzamel gegevens ───────────────────────────────────────
    cycles = len(report_data)
    if cycles == 0:
        return "<html><body><h1>Geen RSI data</h1></body></html>"

    first = report_data[0]
    last = report_data[-1]

    quality_labels = [f"Cycle {r.get('cycle', i + 1)}" for i, r in enumerate(report_data)]
    quality_before = [r.get("quality_before", 0) for r in report_data]
    quality_after = [r.get("quality_after", 0) for r in report_data]
    improvements = [r.get("improvement", 0) for r in report_data]

    total_auto = sum(r.get("succeeded", 0) for r in report_data)
    total_llm = sum(r.get("queued", 0) for r in report_data)
    total_attempted = sum(r.get("attempted", 0) for r in report_data)
    total_failed = sum(r.get("failed", 0) for r in report_data)
    total_cross = sum(r.get("cross_file_issues", 0) for r in report_data)

    # Pattern/learn data
    patterns_list = memory_data.get("patterns", [])
    weights = memory_data.get("weights", {})
    llm_fixes = memory_data.get("llm_fixes_count", 0)

    # Top patterns
    top_patterns = sorted(
        patterns_list, 
        key=lambda p: p.get("times_success", 0) / max(1, p.get("times_tried", 1)),
        reverse=True
    )[:8]

    # Weight bars data
    weight_labels = list(weights.keys()) if weights else []
    weight_values = [weights[k] for k in weight_labels] if weight_labels else []

    # Focus per cycle
    foci = [r.get("focus", "all") for r in report_data]

    # Status badges
    statuses = [r.get("status", "unknown") for r in report_data]

    # ── Bouw HTML ───────────────────────────────────────────────

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RSI v2.0 — Dashboard | ToolCase</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {{
  --bg: #120720;
  --bg-card: rgba(255,255,255,0.03);
  --bg-card-hover: rgba(255,255,255,0.05);
  --border: rgba(255,255,255,0.06);
  --text: #e2e8f0;
  --text-dim: #94a3b8;
  --purple: #A855F7;
  --pink: #EC4899;
  --blue: #3B82F6;
  --cyan: #06B6D4;
  --green: #22c55e;
  --yellow: #eab308;
  --red: #ef4444;
  --orange: #f97316;
  --gradient-1: linear-gradient(135deg, #A855F7, #EC4899);
  --gradient-2: linear-gradient(135deg, #3B82F6, #06B6D4);
  --gradient-3: linear-gradient(135deg, #22c55e, #06B6D4);
  --radius: 12px;
  --radius-sm: 8px;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
  background: var(--bg);
  color: var(--text);
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  line-height: 1.5;
  min-height: 100vh;
}}

/* Subtle grid background */
body::before {{
  content: '';
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(rgba(168,85,247,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(168,85,247,0.03) 1px, transparent 1px);
  background-size: 60px 60px;
  pointer-events: none;
  z-index: 0;
}}

.container {{
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
  position: relative;
  z-index: 1;
}}

/* Header */
.header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 32px;
  padding: 24px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  backdrop-filter: blur(20px);
}}

.header-left h1 {{
  font-size: 28px;
  background: var(--gradient-1);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-weight: 700;
}}

.header-left .subtitle {{
  color: var(--text-dim);
  font-size: 14px;
  margin-top: 4px;
}}

.header-right {{
  display: flex;
  gap: 12px;
  align-items: center;
}}

.badge {{
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}}

.badge-active {{ background: rgba(34,197,94,0.15); color: var(--green); }}
.badge-pending {{ background: rgba(234,179,8,0.15); color: var(--yellow); }}
.badge-failed {{ background: rgba(239,68,68,0.15); color: var(--red); }}

/* Stat Cards Grid */
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
}}

.stat-card {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  transition: all 0.2s;
  backdrop-filter: blur(20px);
}}

.stat-card:hover {{
  background: var(--bg-card-hover);
  transform: translateY(-2px);
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}}

.stat-card .icon {{ font-size: 28px; margin-bottom: 8px; }}
.stat-card .value {{
  font-size: 32px;
  font-weight: 700;
  background: var(--gradient-1);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}}
.stat-card .value.green {{ background: var(--gradient-3); -webkit-background-clip: text; background-clip: text; }}
.stat-card .value.blue {{ background: var(--gradient-2); -webkit-background-clip: text; background-clip: text; }}

.stat-card .label {{
  color: var(--text-dim);
  font-size: 13px;
  margin-top: 4px;
}}

.stat-card .delta {{
  font-size: 12px;
  margin-top: 6px;
}}
.stat-card .delta.up {{ color: var(--green); }}
.stat-card .delta.down {{ color: var(--red); }}

/* Charts Grid */
.charts-grid {{
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  margin-bottom: 32px;
}}

@media (max-width: 900px) {{
  .charts-grid {{ grid-template-columns: 1fr; }}
}}

.chart-card {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  backdrop-filter: blur(20px);
}}

.chart-card h3 {{
  font-size: 16px;
  margin-bottom: 16px;
  color: var(--text);
  font-weight: 600;
}}

.chart-container {{
  position: relative;
  height: 300px;
}}

.chart-container canvas {{
  width: 100% !important;
}}

/* Tables */
.table-card {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  margin-bottom: 16px;
  backdrop-filter: blur(20px);
}}

.table-card h3 {{
  font-size: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  font-weight: 600;
}}

table {{
  width: 100%;
  border-collapse: collapse;
}}

th {{
  text-align: left;
  padding: 10px 20px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-dim);
  border-bottom: 1px solid var(--border);
}}

td {{
  padding: 12px 20px;
  font-size: 14px;
  border-bottom: 1px solid rgba(255,255,255,0.03);
}}

tr:hover td {{ background: rgba(255,255,255,0.02); }}

/* Severity dots */
.sev-dot {{
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 6px;
}}
.sev-critical {{ background: var(--red); box-shadow: 0 0 8px rgba(239,68,68,0.5); }}
.sev-high {{ background: var(--orange); box-shadow: 0 0 6px rgba(249,115,22,0.4); }}
.sev-medium {{ background: var(--yellow); }}
.sev-low {{ background: var(--blue); }}
.sev-info {{ background: var(--cyan); }}

/* Pattern bars */
.pattern-bar {{
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}}
.pattern-bar .bar-fill {{
  height: 8px;
  border-radius: 4px;
  transition: width 0.3s;
}}
.pattern-bar .bar-label {{
  font-size: 12px;
  color: var(--text-dim);
  min-width: 80px;
}}
.pattern-bar .bar-value {{
  font-size: 12px;
  color: var(--text);
  min-width: 40px;
  text-align: right;
}}

/* Section titles */
.section-title {{
  font-size: 20px;
  font-weight: 700;
  margin: 32px 0 16px;
  color: var(--text);
}}

/* Footer */
.footer {{
  text-align: center;
  padding: 32px;
  color: var(--text-dim);
  font-size: 12px;
  border-top: 1px solid var(--border);
  margin-top: 40px;
}}

.footer .gradient-text {{
  background: var(--gradient-1);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}}

/* Focus badges */
.focus-badge {{
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}}
.focus-all {{ background: rgba(168,85,247,0.2); color: var(--purple); }}
.focus-docs {{ background: rgba(59,130,246,0.2); color: var(--blue); }}
.focus-types {{ background: rgba(6,182,212,0.2); color: var(--cyan); }}
.focus-security {{ background: rgba(239,68,68,0.2); color: var(--red); }}
.focus-tests {{ background: rgba(34,197,94,0.2); color: var(--green); }}

/* Status indicators */
.status-ok {{ color: var(--green); }}
.status-warn {{ color: var(--yellow); }}
.status-err {{ color: var(--red); }}

/* Glow effects */
.glow-purple {{ box-shadow: 0 0 20px rgba(168,85,247,0.15); }}
.glow-pink {{ box-shadow: 0 0 20px rgba(236,72,153,0.15); }}
.glow-blue {{ box-shadow: 0 0 20px rgba(59,130,246,0.15); }}

@keyframes pulse {{
  0%, 100% {{ opacity: 1; }}
  50% {{ opacity: 0.5; }}
}}

.pulse {{ animation: pulse 2s infinite; }}
</style>
</head>
<body>

<div class="container">

<!-- Header -->
<div class="header glow-purple">
  <div class="header-left">
    <h1>⚡ RSI v2.0 — Recursive Self-Improvement</h1>
    <div class="subtitle">ToolCase · SmokerGreenOG · {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
  </div>
  <div class="header-right">
    <span class="badge badge-active">v2.0</span>
    <span class="badge badge-active">{cycles} cycli</span>
    <span class="badge badge-{'active' if last.get('status','') != 'failed' else 'failed'}">{last.get('status', '?').upper()}</span>
  </div>
</div>

<!-- Stat Cards -->
<div class="stats-grid">
  <div class="stat-card glow-purple">
    <div class="icon">📊</div>
    <div class="value">{last.get('quality_after', 0):.4f}</div>
    <div class="label">Kwaliteitsscore</div>
    <div class="delta {'up' if last.get('improvement', 0) > 0 else 'down'}">{last.get('improvement', 0):+.4f}</div>
  </div>
  <div class="stat-card glow-blue">
    <div class="icon">📁</div>
    <div class="value blue">{last.get('files_analyzed', 0)}</div>
    <div class="label">Bestanden geanalyseerd</div>
  </div>
  <div class="stat-card glow-pink">
    <div class="icon">🔧</div>
    <div class="value">{total_auto}</div>
    <div class="label">Auto-fixes toegepast</div>
    <div class="delta up">RSI direct</div>
  </div>
  <div class="stat-card glow-purple">
    <div class="icon">🤖</div>
    <div class="value">{total_llm}</div>
    <div class="label">LLM fixes queued</div>
    <div class="delta up">Hermes</div>
  </div>
  <div class="stat-card">
    <div class="icon">🔄</div>
    <div class="value">{total_cross}</div>
    <div class="label">Cross-file issues</div>
  </div>
  <div class="stat-card">
    <div class="icon">🧠</div>
    <div class="value">{len(patterns_list)}</div>
    <div class="label">Geleerde patronen</div>
    <div class="delta up">{llm_fixes} LLM fixes totaal</div>
  </div>
</div>

<!-- Charts -->
<div class="charts-grid">
  <div class="chart-card glow-purple">
    <h3>📈 Kwaliteit per Cyclus</h3>
    <div class="chart-container">
      <canvas id="qualityChart"></canvas>
    </div>
  </div>
  <div class="chart-card glow-pink">
    <h3>🎯 Fix Verdeling</h3>
    <div class="chart-container">
      <canvas id="fixChart"></canvas>
    </div>
  </div>
</div>

<!-- Weight Chart -->
<div class="chart-card glow-blue" style="margin-bottom: 32px;">
  <h3>⚖️ Prioriteitsgewichten (Adaptief)</h3>
  <div class="chart-container" style="height: 250px;">
    <canvas id="weightChart"></canvas>
  </div>
</div>

<!-- Cycle Details Table -->
<div class="table-card">
  <h3>📋 Cyclus Details</h3>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Focus</th>
        <th>Kwaliteit Voor</th>
        <th>Kwaliteit Na</th>
        <th>Δ</th>
        <th>Auto</th>
        <th>LLM</th>
        <th>Cross-file</th>
        <th>Tijd</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>"""

    for r in report_data:
        cyc = r.get('cycle', '?')
        focus = r.get('focus', 'all')
        qb = r.get('quality_before', 0)
        qa = r.get('quality_after', 0)
        delta = r.get('improvement', 0)
        auto = r.get('succeeded', 0)
        llm = r.get('queued', 0)
        cross = r.get('cross_file_issues', 0)
        dur = r.get('duration_s', 0)
        status = r.get('status', '?')
        delta_class = 'status-ok' if delta > 0 else ('status-err' if delta < 0 else '')
        status_class = 'status-ok' if status == 'completed' else ('status-warn' if status == 'pending_llm' else 'status-err')

        html += f"""
      <tr>
        <td><strong>#{cyc}</strong></td>
        <td><span class="focus-badge focus-{focus}">{focus}</span></td>
        <td>{qb:.4f}</td>
        <td>{qa:.4f}</td>
        <td class="{delta_class}">{delta:+.4f}</td>
        <td>{auto}</td>
        <td>{llm}</td>
        <td>{cross}</td>
        <td>{dur:.1f}s</td>
        <td class="{status_class}">● {status.upper()}</td>
      </tr>"""

    html += f"""
    </tbody>
  </table>
</div>

<!-- Top Patterns -->
<div class="table-card">
  <h3>🧠 Top Geleerde Patronen</h3>
  <table>
    <thead>
      <tr><th>Patroon</th><th>Categorie</th><th>Success Rate</th><th>Verbetering</th><th>Keren Geprobeerd</th></tr>
    </thead>
    <tbody>"""

    if top_patterns:
        for p in top_patterns:
            desc = p.get('description', '?')[:80]
            cat = p.get('category', '?')
            times = p.get('times_tried', 0)
            succ = p.get('times_success', 0)
            rate = succ / max(1, times) * 100
            avg_imp = p.get('avg_improvement', 0)
            rate_color = 'var(--green)' if rate > 70 else ('var(--yellow)' if rate > 40 else 'var(--red)')
            html += f"""
      <tr>
        <td>{desc}</td>
        <td><span class="focus-badge focus-{cat[:10]}">{cat}</span></td>
        <td style="color: {rate_color}">{rate:.0f}%</td>
        <td>{avg_imp:+.3f}</td>
        <td>{times}x</td>
      </tr>"""
    else:
        html += """<tr><td colspan="5" style="color: var(--text-dim); text-align: center;">Nog geen patronen geleerd — draai de RSI om te starten</td></tr>"""

    html += """
    </tbody>
  </table>
</div>"""

    # Weight Distribution
    if weight_labels:
        html += f"""
<div class="table-card">
  <h3>⚖️ Gewichtsdistributie</h3>
  <div style="padding: 20px;">"""
        max_weight = max(weight_values) if weight_values else 1
        for label, value in zip(weight_labels, weight_values):
            pct = (value / max_weight) * 100
            color = "var(--purple)" if value > 5 else ("var(--blue)" if value > 3 else "var(--cyan)")
            html += f"""
    <div class="pattern-bar">
      <span class="bar-label">{label}</span>
      <div style="flex:1; background: rgba(255,255,255,0.05); border-radius: 4px; height: 8px;">
        <div class="bar-fill" style="width: {pct:.0f}%; background: {color};"></div>
      </div>
      <span class="bar-value">{value:.1f}</span>
    </div>"""
        html += """
  </div>
</div>"""

    # Footer
    html += f"""
<div class="footer">
  <p><span class="gradient-text">⚡ ToolCase RSI v2.0</span> — Recursive Self-Improvement</p>
  <p style="margin-top: 4px;">SmokerGreenOG · {datetime.now().year} · {cycles} cycli · {len(patterns_list)} geleerde patronen</p>
</div>

</div>

<!-- Chart.js -->
<script>
// Color palette
const purple = '#A855F7';
const pink = '#EC4899';
const blue = '#3B82F6';
const cyan = '#06B6D4';
const green = '#22c55e';
const yellow = '#eab308';
const red = '#ef4444';

Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';
Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";

// Quality Chart
new Chart(document.getElementById('qualityChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(quality_labels)},
    datasets: [{{
      label: 'Kwaliteit Voor',
      data: {json.dumps(quality_before)},
      borderColor: blue,
      backgroundColor: 'rgba(59,130,246,0.1)',
      fill: true,
      tension: 0.3,
      borderWidth: 2,
      pointBackgroundColor: blue,
      pointRadius: 5,
    }}, {{
      label: 'Kwaliteit Na',
      data: {json.dumps(quality_after)},
      borderColor: purple,
      backgroundColor: 'rgba(168,85,247,0.1)',
      fill: true,
      tension: 0.3,
      borderWidth: 2,
      pointBackgroundColor: purple,
      pointRadius: 5,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'bottom', labels: {{ usePointStyle: true, padding: 20 }} }},
      tooltip: {{ mode: 'index', intersect: false }}
    }},
    scales: {{
      y: {{ min: 0, max: 1, ticks: {{ callback: v => v.toFixed(3) }} }}
    }}
  }}
}});

// Fix Distribution Chart
new Chart(document.getElementById('fixChart'), {{
  type: 'doughnut',
  data: {{
    labels: ['Auto-fixes ({total_auto})', 'LLM-queued ({total_llm})', 'Failed ({total_failed})'],
    datasets: [{{
      data: [{total_auto}, {total_llm}, {total_failed}],
      backgroundColor: [purple, cyan, red + '44'],
      borderColor: [purple, cyan, red],
      borderWidth: 1,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'bottom', labels: {{ usePointStyle: true, padding: 16 }} }}
    }}
  }}
}});

// Weight Chart
new Chart(document.getElementById('weightChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(weight_labels)},
    datasets: [{{
      label: 'Prioriteitsgewicht',
      data: {json.dumps(weight_values)},
      backgroundColor: weight_values.map(v => v > 5 ? purple : v > 3 ? blue : cyan),
      borderRadius: 6,
      borderWidth: 0,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: 'y',
    plugins: {{
      legend: {{ display: false }}
    }},
    scales: {{
      x: {{ grid: {{ display: false }} }}
    }}
  }}
}});
</script>

</body>
</html>"""

    return html


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RSI HTML Report Generator — Dark-themed dashboard",
    )
    parser.add_argument("--input", "-i",
                        help="Input JSON rapport (default: laatste in .rsi_reports/)")
    parser.add_argument("--output", "-o", default=str(DEFAULT_OUTPUT),
                        help=f"Output HTML path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--open", action="store_true",
                        help="Open in browser na generatie")

    args = parser.parse_args()

    # Find input
    if args.input:
        input_path = Path(args.input)
    else:
        input_path = _find_latest_report()

    if not input_path or not input_path.exists():
        print("❌ Geen RSI rapport gevonden. Draai eerst de RSI.")
        sys.exit(1)

    # Load data
    print(f"📂 Laden: {input_path}")
    report_data = _load_json(input_path)

    # Als het een lijst van reports is (van run()), wrap indien nodig
    if isinstance(report_data, dict):
        # Het kan de {version, focus, reports: [...]} wrapper zijn
        if "reports" in report_data:
            report_data = report_data["reports"]
        else:
            report_data = [report_data]
    elif not isinstance(report_data, list):
        print("❌ Onverwacht JSON formaat")
        sys.exit(1)

    # Load memory
    memory_data = _load_metrics(TOOLCASE_DIR)

    # Generate
    html = generate_html(report_data, memory_data, Path(args.output))

    # Write
    output_path = Path(args.output)
    output_path.write_text(html, encoding="utf-8")
    print(f"✅ Rapport gegenereerd: {output_path}")
    print(f"   📊 {len(report_data)} cycli  |  🧠 {len(memory_data.get('patterns', []))} patronen")

    # Open
    if args.open:
        webbrowser.open(f"file:///{output_path.as_posix()}")


if __name__ == "__main__":
    main()
