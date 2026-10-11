"""The .drums chart engine: parsing, validation errors, rendering, golden pages."""

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from drum_agent.drumchart.parser import ChartError, parse_chart
from drum_agent.drumchart.render import load, render_html, summary

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
REFERENCES = ROOT / ".claude" / "skills" / "drum-chart" / "references"
GOLDEN = Path(__file__).parent / "golden" / "pages.json"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.parametrize("name", ["stress", "night-drive"])
def test_example_pages_match_golden(name):
    """Engraving changes must be deliberate: re-record with DRUM_AGENT_UPDATE_GOLDEN=1."""
    chart = load(EXAMPLES / f"{name}.drums")
    got = {name: _sha(render_html(chart)), f"{name}.artifact": _sha(render_html(chart, standalone=False))}
    golden = json.loads(GOLDEN.read_text())
    if os.environ.get("DRUM_AGENT_UPDATE_GOLDEN"):
        golden.update(got)
        GOLDEN.write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n")
    assert {k: golden.get(k) for k in got} == got


def test_summary_lists_sections_and_total():
    chart = load(EXAMPLES / "night-drive.drums")
    text = summary(chart)
    assert "Night Drive" in text and "total:" in text
    assert len(chart.sections) >= 3


def _gallery(md: str) -> str:
    """Every ```-block pattern of grooves.md as one chart, one section per pattern."""
    pats = []
    for block in re.findall(r"```\n(.*?)```", md, re.S):
        cur = []
        for line in block.splitlines():
            if line.startswith("pattern "):
                if cur:
                    pats.append(cur)
                cur = [line]
            elif cur and line.strip() and not line.startswith("#"):
                cur.append(line)
            elif line.startswith("#") and cur:
                pats.append(cur)
                cur = []
        if cur:
            pats.append(cur)
    out = ["title: Groove Library", "artist: drum-agent", "tempo: 100", "time: 4/4", ""]
    meters = {}
    for p in pats:
        m = re.search(r"\btime (\d+/\d+(?: \d+(?:\+\d+)+)?)", p[0])
        meters[p[0].split()[1]] = m.group(1) if m else "4/4"
        out += p + [""]
    for name, meter in meters.items():
        out += [f"section {name}", f"  @time {meter}", f"  play {name}", ""]
    return "\n".join(out)


def test_groove_library_parses_and_renders():
    chart = parse_chart(_gallery((REFERENCES / "grooves.md").read_text(encoding="utf-8")))
    assert len(chart.patterns) >= 30
    assert "<svg" in render_html(chart)


def test_format_reference_worked_example_parses():
    text = (REFERENCES / "format.md").read_text(encoding="utf-8")
    example = text.split("## 8. Worked example")[1].split("```")[1]
    assert parse_chart(example).sections


@pytest.mark.parametrize(
    "body, message",
    [
        ("pattern a\n  HH  x-x- x-x- x-x-\nsection A\n  play a\n", "4/4 needs 4"),
        ("pattern a\n  SN  o--- ---- ---- ----\nsection A\n  play a\n", "not valid"),
        ("section A\n  play nope\n", "unknown pattern"),
    ],
)
def test_errors_point_at_the_problem(body, message):
    with pytest.raises(ChartError, match=message):
        parse_chart("title: T\ntempo: 100\ntime: 4/4\n\n" + body)


def test_page_carries_its_source_for_round_trip():
    from drum_agent.drumchart.render import extract

    source = (EXAMPLES / "night-drive.drums").read_text(encoding="utf-8")
    source = source.replace("title: Night Drive", "title: Night Drive\nnotes: tricky </script> text")
    page = render_html(parse_chart(source), source=source)
    assert extract(page) == source
    assert extract(render_html(parse_chart(source))) is None
