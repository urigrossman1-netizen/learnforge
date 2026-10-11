"""Chart corrections: one-bar edits, version history (undo/redo/restore), and change lists."""

from pathlib import Path

import pytest

from drum_agent import cli
from drum_agent.drumchart import edit
from drum_agent.drumchart.parser import parse_chart

CHART = """title: Edit Test
tempo: 100
time: 4/4

pattern groove
  HH  x-x- x-x- x-x- x-x-
  SN  ---- x--- ---- x---
  BD  x--- ---- x--- ----

pattern fill
  SN  ---- ---- xxxx xxxx
  BD  x--- ---- ---- ----

section Verse
  play groove x3
  play fill @fill @confidence medium "toms?"
"""


def test_set_bar_changes_only_that_bar():
    new = edit.set_bar(CHART, 2, "HH x-x- x-x- x-x- x-o-; SN ---- x--- ---- x--g; BD x--- ---- x--- ----")
    old_bars, new_bars = parse_chart(CHART).bars, parse_chart(new).bars
    assert len(new_bars) == 4
    assert [b.rows for b in new_bars[::2]] == [b.rows for b in old_bars[::2]]  # bars 1 and 3 untouched
    assert edit.diff(CHART, new) == ["bar 2: HH 4& x->o; SN +4a(g)"]


def test_set_bar_keeps_the_bars_marks():
    new = edit.set_bar(CHART, 4, "SN xxxx xxxx xxxx xxxx; FT ---- ---- ---- x---")
    bar = parse_chart(new).bars[3]
    assert bar.has_directive("fill") and bar.confidence == "medium"
    with pytest.raises(ValueError, match="unknown instrument"):
        edit.set_bar(CHART, 1, "ZZ x--- ---- ---- ----")
    with pytest.raises(ValueError, match="does not exist"):
        edit.set_bar(CHART, 9, "SN x--- ---- ---- ----")


def test_history_undo_redo_restore(tmp_path):
    path = tmp_path / "chart.drums"
    path.write_text(CHART)
    assert cli.main(["bar", str(path), "1", "--set", "SN x--- x--- x--- x---"]) == 0
    edited = path.read_text()
    assert edited != CHART and len(edit.versions(path)) == 2
    assert cli.main(["undo", str(path)]) == 0 and path.read_text() == CHART
    assert cli.main(["redo", str(path)]) == 0 and path.read_text() == edited
    assert cli.main(["restore", str(path), "1"]) == 0 and path.read_text() == CHART
    assert cli.main(["restore", str(path), "9"]) == 2  # no such version


def test_diff_command(tmp_path, capsys):
    a, b = tmp_path / "a.drums", tmp_path / "b.drums"
    a.write_text(CHART)
    b.write_text(CHART.replace("section Verse", "section Verse 1"))
    assert cli.main(["diff", str(a), str(b)]) == 0
    assert "Verse 1" in capsys.readouterr().out
