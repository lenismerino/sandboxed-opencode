#!/usr/bin/env python3
"""Generate a static HTML dashboard from monitoring JSONL logs."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(os.environ.get("LOG_DIR", "/home/agent/projects/logs"))
PUBLIC_DIR = Path(os.environ.get("DASHBOARD_PUBLIC_DIR", "/tmp/dashboard-public"))
OUTPUT = PUBLIC_DIR / "index.html"

PROJECT_NAME = os.environ.get("PROJECT_NAME", "unknown")
LLM_SOURCE = os.environ.get("LLM_SOURCE", "unknown")
LLM_MODEL = (
    os.environ.get("LM_STUDIO_MODEL")
    or os.environ.get("FASTFLOW_MODEL")
    or os.environ.get("OLLAMA_MODEL")
    or "unknown"
)
OPERATION_MODE = os.environ.get("OPERATION_MODE", "interactive")
OPENCODE_INTERFACE = os.environ.get("OPENCODE_INTERFACE", "web")


def read_jsonl(path: Path, max_lines: int = 5000) -> list[dict]:
    if not path.exists():
        return []
    lines = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(lines) >= max_lines:
                break
    return lines


def compute_elapsed(records: list[list[dict]]) -> str:
    earliest = None
    for group in records:
        for r in group:
            ts = r.get("timestamp")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if earliest is None or dt < earliest:
                        earliest = dt
                except ValueError:
                    continue
    if earliest is None:
        return "N/A"
    delta = datetime.now(timezone.utc) - earliest
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def svg_line_chart(
    data: list[float], width: int = 600, height: int = 120, color: str = "#3b82f6",
    y_label: str = "", max_points: int = 200,
) -> str:
    if not data:
        return '<p style="color:#888">No data yet.</p>'
    if len(data) > max_points:
        step = len(data) / max_points
        data = [data[int(i * step)] for i in range(max_points)]
    min_v = min(data)
    max_v = max(data)
    span = max_v - min_v if max_v != min_v else 1
    pad = 10
    cw = width - 2 * pad
    ch = height - 2 * pad
    points = []
    for i, v in enumerate(data):
        x = pad + (i / max(len(data) - 1, 1)) * cw
        y = pad + ch - ((v - min_v) / span) * ch
        points.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(points)
    return (
        f'<svg width="{width}" height="{height}" style="background:#1e1e2e;border-radius:8px">'
        f'<text x="{pad}" y="{pad + 10}" fill="#888" font-size="11">{max_v:.1f}</text>'
        f'<text x="{pad}" y="{height - pad + 2}" fill="#888" font-size="11">{min_v:.1f}</text>'
        f'<text x="{width - pad}" y="{height - pad + 2}" fill="#888" font-size="11" text-anchor="end">{y_label}</text>'
        f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{polyline}"/>'
        f"</svg>"
    )


def svg_bar_chart(
    data: list[tuple[str, int]], width: int = 600, height: int = 120,
    color: str = "#ef4444", max_bars: int = 48,
) -> str:
    if not data:
        return '<p style="color:#888">No data yet.</p>'
    if len(data) > max_bars:
        data = data[-max_bars:]
    max_v = max(v for _, v in data)
    if max_v == 0:
        max_v = 1
    pad = 10
    cw = width - 2 * pad
    ch = height - 2 * pad
    bar_w = max(cw / len(data) - 2, 1)
    bars = []
    for i, (_, v) in enumerate(data):
        bx = pad + i * (cw / len(data))
        bh = (v / max_v) * ch
        by = pad + ch - bh
        bars.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" fill="{color}" rx="2"/>')
    rects = "".join(bars)
    return (
        f'<svg width="{width}" height="{height}" style="background:#1e1e2e;border-radius:8px">'
        f'<text x="{pad}" y="{pad + 10}" fill="#888" font-size="11">max: {max(v for _, v in data)}</text>'
        f"{rects}</svg>"
    )


def stat_card(label: str, value: str, color: str = "#3b82f6") -> str:
    return (
        f'<div style="background:#1e1e2e;border-radius:8px;padding:16px 20px;min-width:140px;text-align:center">'
        f'<div style="color:#888;font-size:12px;margin-bottom:4px">{label}</div>'
        f'<div style="color:{color};font-size:24px;font-weight:700">{value}</div></div>'
    )


def build_html(
    resources: list[dict], portscan: list[dict], summaries: list[dict],
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    elapsed = compute_elapsed([resources, portscan, summaries])

    sections = []

    # -- Header --
    sections.append(
        f'<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:24px">'
        f'{stat_card("Project", PROJECT_NAME, "#a78bfa")}'
        f'{stat_card("LLM", f"{LLM_SOURCE} / {LLM_MODEL}", "#38bdf8")}'
        f'{stat_card("Mode", f"{OPERATION_MODE} ({OPENCODE_INTERFACE})", "#34d399")}'
        f'{stat_card("Elapsed", elapsed, "#fbbf24")}'
        f"</div>"
    )

    # -- Resource Usage --
    if resources:
        mem_pcts = [r.get("mem_used_pct", 0) for r in resources]
        proc_counts = [r.get("process_count", 0) for r in resources]
        peak_mem = max(mem_pcts) if mem_pcts else 0
        latest = resources[-1]
        mem_total_mb = latest.get("mem_total_kb", 0) / 1024
        mem_avail_mb = latest.get("mem_available_kb", 0) / 1024

        top_procs_rows = ""
        for p in latest.get("top_processes", [])[:10]:
            cmd = p.get("command", "")[:60]
            top_procs_rows += (
                f'<tr><td>{p.get("pid","")}</td><td>{p.get("user","")}</td>'
                f'<td>{p.get("cpu",0):.1f}%</td><td>{p.get("mem",0):.1f}%</td>'
                f"<td>{cmd}</td></tr>"
            )

        sections.append(
            f'<h2>Resource Usage</h2>'
            f'<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px">'
            f'{stat_card("Peak Memory", f"{peak_mem:.1f}%", "#ef4444")}'
            f'{stat_card("Current Memory", f"{mem_pcts[-1]:.1f}%")}'
            f'{stat_card("Total RAM", f"{mem_total_mb:.0f} MB")}'
            f'{stat_card("Available", f"{mem_avail_mb:.0f} MB")}'
            f'{stat_card("Processes", str(latest.get("process_count", 0)))}'
            f'{stat_card("Snapshots", str(len(resources)), "#888")}'
            f"</div>"
            f"<h3>Memory Usage Over Time</h3>"
            f'{svg_line_chart(mem_pcts, y_label="% used")}'
            f"<h3>Process Count Over Time</h3>"
            f'{svg_line_chart(proc_counts, color="#34d399", y_label="count")}'
            f"<h3>Top Processes (Latest)</h3>"
            f'<table><thead><tr><th>PID</th><th>User</th><th>CPU</th><th>MEM</th><th>Command</th></tr></thead>'
            f"<tbody>{top_procs_rows}</tbody></table>"
        )

    # -- Port Scanning --
    if portscan:
        total_scans = len(portscan)
        warnings = [r for r in portscan if r.get("status") == "warning"]
        warning_count = len(warnings)

        hourly: dict[str, int] = {}
        for r in portscan:
            ts = r.get("timestamp", "")[:13]
            if r.get("status") == "warning":
                hourly[ts] = hourly.get(ts, 0) + 1
            else:
                hourly.setdefault(ts, 0)
        hourly_data = sorted(hourly.items())

        unexpected_rows = ""
        if warnings:
            latest_warn = warnings[-1]
            for u in latest_warn.get("unexpected", []):
                unexpected_rows += f'<tr><td>{u.get("address","")}</td><td>{u.get("process","")}</td></tr>'

        sections.append(
            f"<h2>Port Scanning</h2>"
            f'<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px">'
            f'{stat_card("Total Scans", str(total_scans))}'
            f'{stat_card("Warnings", str(warning_count), "#ef4444" if warning_count > 0 else "#34d399")}'
            f"</div>"
            f"<h3>Warnings Over Time</h3>"
            f"{svg_bar_chart(hourly_data)}"
        )
        if unexpected_rows:
            sections.append(
                f"<h3>Latest Unexpected Listeners</h3>"
                f'<table><thead><tr><th>Address</th><th>Process</th></tr></thead>'
                f"<tbody>{unexpected_rows}</tbody></table>"
            )

    # -- Security Summaries --
    if summaries:
        summary_rows = ""
        for s in summaries[-24:]:
            ts = s.get("timestamp", "")[:19]
            mt = s.get("mem_total_kb", 0) / 1024
            ma = s.get("mem_available_kb", 0) / 1024
            summary_rows += (
                f"<tr><td>{ts}</td><td>{s.get('process_count', 0)}</td>"
                f"<td>{mt:.0f} MB</td><td>{ma:.0f} MB</td>"
                f"<td>{s.get('portscan_warnings', 0)}</td>"
                f"<td>{s.get('resource_snapshots', 0)}</td></tr>"
            )
        listeners_html = ""
        if summaries[-1].get("listeners"):
            items = "".join(f"<li>{l}</li>" for l in summaries[-1]["listeners"])
            listeners_html = f"<h3>Active Listeners</h3><ul>{items}</ul>"

        sections.append(
            f"<h2>Security Summaries</h2>"
            f'<table><thead><tr><th>Time</th><th>Procs</th><th>Total RAM</th>'
            f"<th>Available</th><th>Port Warnings</th><th>Snapshots</th></tr></thead>"
            f"<tbody>{summary_rows}</tbody></table>"
            f"{listeners_html}"
        )

    # -- No data --
    if not resources and not portscan and not summaries:
        sections.append(
            '<div style="text-align:center;padding:60px;color:#888">'
            "<h2>No monitoring data yet</h2>"
            "<p>Enable PORTSCAN_ENABLED, RESOURCE_MONITOR_ENABLED, or AUTOLOG_ENABLED in .env</p>"
            "</div>"
        )

    body = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{os.environ.get('DASHBOARD_REFRESH_INTERVAL', '30')}">
<title>{PROJECT_NAME} — Sandbox Dashboard</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
         background: #0f0f1a; color: #e0e0e0; padding: 24px; max-width: 960px; margin: 0 auto; }}
  h1 {{ color: #a78bfa; margin-bottom: 8px; font-size: 22px; }}
  h2 {{ color: #38bdf8; margin: 24px 0 12px; font-size: 18px; border-bottom: 1px solid #2a2a3a; padding-bottom: 6px; }}
  h3 {{ color: #888; margin: 16px 0 8px; font-size: 14px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 16px; font-size: 13px; }}
  th, td {{ padding: 6px 10px; text-align: left; border-bottom: 1px solid #2a2a3a; }}
  th {{ color: #888; font-weight: 600; }}
  td {{ color: #ccc; }}
  tr:hover td {{ background: #1e1e2e; }}
  svg {{ display: block; margin-bottom: 12px; width: 100%; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ padding: 4px 0; color: #ccc; font-size: 13px; }}
  li::before {{ content: "\\25CF "; color: #38bdf8; }}
  .footer {{ margin-top: 32px; padding-top: 12px; border-top: 1px solid #2a2a3a; color: #555; font-size: 12px; text-align: center; }}
</style>
</head>
<body>
<h1>{PROJECT_NAME} — Sandbox Dashboard</h1>
{body}
<div class="footer">Last updated: {now} &middot; Auto-refresh: {os.environ.get('DASHBOARD_REFRESH_INTERVAL', '30')}s</div>
</body>
</html>"""


def main() -> None:
    resources = read_jsonl(LOG_DIR / "resources.jsonl")
    portscan = read_jsonl(LOG_DIR / "portscan.jsonl")
    summaries = read_jsonl(LOG_DIR / "security_summary.jsonl")

    html = build_html(resources, portscan, summaries)

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html)


if __name__ == "__main__":
    main()
