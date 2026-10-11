"""Validate and render .drums charts: form summary, HTML page, PNG/PDF screenshots.

The summary lists every section with its bar range, start time at the chart's
tempo and the total length, so the chart's form can be compared with the
recording (e.g. 'length: 4:17' in the header vs. the computed total).
"""

from __future__ import annotations

from pathlib import Path

from .model import Chart
from .parser import ChartError, parse_chart

__all__ = ["ChartError", "fmt", "load", "render_html", "summary", "timing_warnings"]


def fmt(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def load(path: str | Path) -> Chart:
    """Parse a .drums file; raises ChartError with a line number on problems."""
    return parse_chart(Path(path).read_text(encoding="utf-8"))


def timing_warnings(chart: Chart, tolerance: float = 4.0) -> list[str]:
    """Sections whose computed start drifts from their recorded `at` timestamp."""
    warn = []
    for s in chart.sections:
        if s.at and ":" in s.at:
            try:
                mm, ss = s.at.split(":")
                rec = int(mm) * 60 + float(ss)
            except ValueError:
                continue
            diff = s.bars[0].start_time - rec
            if abs(diff) > tolerance:
                warn.append(
                    f"{s.name}: chart reaches it at {fmt(s.bars[0].start_time)} but the recording has it at {s.at} "
                    f"({diff:+.0f}s) — check bar counts / tempo / count-in offset"
                )
    return warn


def summary(chart: Chart) -> str:
    out = []
    m = chart.meta
    out.append(f"{m.get('title', '?')} — {m.get('artist', '?')}   tempo {m.get('tempo', '?')}   time {m.get('time', '4/4')}")
    out.append(f"{'#':>3}  {'section':<22} {'bars':>9} {'count':>5}  {'start':>6}  {'at(rec)':>7}  conf")
    for i, s in enumerate(chart.sections, 1):
        b0 = s.bars[0].number
        last = s.bars[-1]
        b1 = last.number + (last.rest_bars - 1 if last.rest_bars else 0)
        n = b1 - b0 + 1
        out.append(
            f"{i:>3}  {s.name[:22]:<22} {b0:>4}-{b1:<4} {n:>5}  {fmt(s.bars[0].start_time):>6}  {s.at or '-':>7}  {s.confidence or '-'}"
        )
    total = float(m.get("_total_seconds", 0))
    out.append(
        f"total: {m.get('_total_bars')} bars, {fmt(total)} at the written tempo"
        + (f"  (recording length: {m['length']})" if m.get("length") else "")
    )
    warn = timing_warnings(chart)
    if warn:
        out.append("timing check:")
        out.extend(f"  ! {w}" for w in warn)
    return "\n".join(out)


def render_html(chart: Chart, *, standalone: bool = True, source: str | None = None) -> str:
    """The zoomable chart page; standalone=False gives the body-only Artifact variant.

    With `source` (the .drums text) the page carries its own chart source, so
    `drum-agent extract` can turn a published page back into an editable chart.
    """
    from .page import render_page

    return render_page(chart, standalone=standalone, source=source)


def extract(page_html: str) -> str | None:
    """The .drums source embedded in a chart page (None for pages made without one)."""
    from .page import extract_source

    return extract_source(page_html)
