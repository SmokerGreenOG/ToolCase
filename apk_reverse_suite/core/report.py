from __future__ import annotations

__maker__ = "SmokerGreenOG"
import _protect

import html
from pathlib import Path
from typing import Any


def risk_score(report: dict[str, Any]) -> dict[str, Any]:
    findings = []
    score = 0
    scan = report.get("scan", {})
    manifest = report.get("manifest", {})
    if scan.get("secrets"):
        score += min(30, 10 + len(scan["secrets"]) * 2)
        findings.append("Possible hardcoded secrets/tokens found")
    if scan.get("risky_strings"):
        score += min(25, len(scan["risky_strings"]) * 4)
        findings.append("Risky API or behavior strings found")
    if manifest.get("suspicious_permissions"):
        score += min(25, len(manifest["suspicious_permissions"]) * 5)
        findings.append("Sensitive Android permissions found")
    if scan.get("native_libs"):
        score += 5
        findings.append("Native libraries present; static Java review may be incomplete")
    if scan.get("urls"):
        score += min(10, len(scan["urls"]))
        findings.append("Network endpoints found")
    return {"score": min(score, 100), "findings": findings}


def html_report(report: dict[str, Any]) -> str:
    def esc(x: Any) -> str:
        return html.escape(str(x))

    def list_block(title: str, values: list[Any], limit: int = 100) -> str:
        if not values:
            return f"<h2>{esc(title)}</h2><p>None found.</p>"
        rows = "".join(f"<li><code>{esc(v)}</code></li>" for v in values[:limit])
        more = f"<p>Showing first {limit} of {len(values)}.</p>" if len(values) > limit else ""
        return f"<h2>{esc(title)}</h2>{more}<ul>{rows}</ul>"

    meta = report.get("metadata", {})
    scan = report.get("scan", {})
    manifest = report.get("manifest", {})
    risk = report.get("risk", {})
    frameworks = report.get("frameworks", [])
    sensitive_permissions = manifest.get("suspicious_permissions", [])

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>APK Reverse Report</title>
<style>
body{{font-family:Arial,Helvetica,sans-serif;background:#111;color:#eee;
margin:32px;line-height:1.45}}
.card{{background:#1b1b1f;border:1px solid #333;border-radius:12px;padding:18px;margin:16px 0}}
code{{background:#2a2a31;padding:2px 5px;border-radius:4px;color:#e7d7ff}}
h1,h2{{color:#d7b8ff}} .score{{font-size:34px;font-weight:bold}}
ul{{max-width:1100px}} li{{margin:5px 0;word-break:break-word}}
.good{{color:#9be49b}} .warn{{color:#ffd479}} .bad{{color:#ff9b9b}}
</style></head><body>
<h1>APK Reverse Engineering Report</h1>
<div class="card">
<div class="score">Risk score: {esc(risk.get('score', 0))}/100</div>
<p>{esc(', '.join(risk.get('findings', [])) or 'No major static indicators found.')}</p>
</div>
<div class="card"><h2>Metadata</h2>
<ul>
<li>APK: <code>{esc(meta.get('apk_path'))}</code></li>
<li>Size: <code>{esc(meta.get('size_bytes'))}</code> bytes</li>
<li>SHA256: <code>{esc(meta.get('sha256'))}</code></li>
</ul></div>
<div class="card"><h2>Manifest</h2>
<ul>
<li>Package: <code>{esc(manifest.get('package'))}</code></li>
<li>Decoded manifest source: <code>{esc(manifest.get('raw_source'))}</code></li>
</ul></div>
<div class="card">{list_block('Detected frameworks', frameworks)}</div>
<div class="card">{list_block('Sensitive permissions', sensitive_permissions)}</div>
<div class="card">{list_block('All permissions', manifest.get('permissions', []), 200)}</div>
<div class="card">{list_block('Components', manifest.get('components', []), 200)}</div>
<div class="card">{list_block('URLs / Endpoints', scan.get('urls', []), 200)}</div>
<div class="card">{list_block('Possible secrets', scan.get('secrets', []), 200)}</div>
<div class="card">{list_block('Risky strings', scan.get('risky_strings', []), 200)}</div>
<div class="card">{list_block('DEX files', scan.get('dex_files', []), 200)}</div>
<div class="card">{list_block('Native libraries', scan.get('native_libs', []), 200)}</div>
<div class="card">{list_block('Certificate/signature files', scan.get('cert_files', []), 200)}</div>
</body></html>"""


def write_html(path: Path, report: dict[str, Any]) -> None:
    path.write_text(html_report(report), encoding="utf-8")
