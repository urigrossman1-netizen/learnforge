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


@pytest.mark.parametrize("name", ["stress", "night-drive", "drum-key"])
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


@pytest.mark.parametrize("name, at_least", [("grooves.md", 40), ("rudiments.md", 10)])
def test_groove_libraries_parse_and_render(name, at_least):
    chart = parse_chart(_gallery((REFERENCES / name).read_text(encoding="utf-8")))
    assert len(chart.patterns) >= at_least
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


# Staff positions measured from the user's Drum Key picture (half-spaces above the bottom
# line: E4 = 0 ... F5 = 8 top line, G5 = 9, A5 = 10 first ledger line, B5 = 11).
DRUM_KEY_PICTURE = {
    "CH": (11, "noteheadCircleX"), "SP": (11, "noteheadDiamondWhite"), "CB": (11, "noteheadTriangleUpBlack"),
    "CR": (10, "noteheadXBlack"), "RD": (9, "noteheadXBlack"), "HH": (8, "noteheadXBlack"),
    "T1": (7, "noteheadBlack"), "T2": (6, "noteheadBlack"), "SN": (5, "noteheadBlack"), "T3": (4, "noteheadBlack"),
    "FT": (3, "noteheadBlack"), "F2": (2, "noteheadBlack"), "BD": (1, "noteheadBlack"), "B2": (0, "noteheadBlack"),
    "HF": (-1, "noteheadXBlack"),
}
DRUM_KEY_TECHNIQUES = {("HH", "o"): "noteheadCircleX", ("HF", "o"): "noteheadCircleX",
                       ("RD", "b"): "noteheadDiamondBlack", ("SN", "c"): "noteheadXBlack"}


def test_default_notation_is_the_users_drum_key():
    from drum_agent.drumchart.model import INSTRUMENTS, staff_key
    from drum_agent.drumchart.notation import build_notehead

    with staff_key():
        assert {c: (INSTRUMENTS[c].pos, INSTRUMENTS[c].head) for c in DRUM_KEY_PICTURE} == DRUM_KEY_PICTURE
        for (code, art), head in DRUM_KEY_TECHNIQUES.items():
            nh = build_notehead(code, art)
            assert (nh.pos, nh.head) == (DRUM_KEY_PICTURE[code][0], head)
    with staff_key("pas"):
        assert (INSTRUMENTS["HH"].pos, INSTRUMENTS["RD"].pos) == (9, 8)  # Weinberg: hi-hat above the staff
    assert INSTRUMENTS["HH"].pos == 9  # restored after the block


def test_unknown_notation_is_rejected():
    chart = parse_chart((EXAMPLES / "night-drive.drums").read_text().replace("tempo:", "notation: tabs\ntempo:", 1))
    with pytest.raises(ValueError, match="unknown notation"):
        render_html(chart)


def test_playability_flags_what_no_drummer_can_play():
    from drum_agent.drumchart.playability import check

    text = """title: T
tempo: 100
time: 4/4

pattern bad
  CR  x--- ---- ---- ----
  HH  x--- ---- o--- ----
  SN  x--- ---- ---- ----
  HF  ---- x--- x--- ----
  B2  ---- x--- ---- ----
  ST  ---- ---- ---- R---

section A
  play bad
"""
    problems = check(parse_chart(text))
    assert any("three hands" in p and "beat 1" in p for p in problems)
    assert any("left foot" in p and "beat 2" in p for p in problems)
    assert any("open hi-hat" in p and "beat 3" in p for p in problems)
    assert any("sticking" in p and "beat 4" in p for p in problems)
    for name in ("night-drive", "drum-key", "stress"):
        assert not [p for p in check(load(EXAMPLES / f"{name}.drums")) if "three hands" in p], name
