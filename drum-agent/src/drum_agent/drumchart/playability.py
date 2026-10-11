"""Can a real drummer play it? Physical checks on a chart (warnings, not errors).

- more than two hand instruments struck at the same moment (three hands);
- the left foot asked to play the hi-hat pedal and a left bass drum at once;
- a hi-hat struck open while the pedal closes it at the same moment;
- sticking letters where no hand plays.
"""

from __future__ import annotations

from collections import defaultdict

from .edit import _where
from .model import INSTRUMENTS, STICKING_ROW, Chart

OPEN_HAT = set("oOh")


def check(chart: Chart) -> list[str]:
    problems = []
    for bar in chart.bars:
        if bar.rest_bars:
            continue
        at = defaultdict(list)
        for h in bar.hits:
            at[h.onset].append(h)
        for onset, hits in sorted(at.items()):
            where = f"bar {bar.number} beat {_where(bar, onset)}"
            hands = sorted({h.inst for h in hits if h.inst in INSTRUMENTS and INSTRUMENTS[h.inst].voice == "up"},
                           key=lambda c: INSTRUMENTS[c].order)
            if len(hands) > 2:
                problems.append(f"{where}: three hands needed at once ({', '.join(hands)})")
            feet = {h.inst: h.art for h in hits if h.inst in ("HF", "B2")}
            if "HF" in feet and "B2" in feet:
                problems.append(f"{where}: the left foot plays the hi-hat pedal and the left bass drum at once")
            if feet.get("HF") in ("x", "X") and any(h.inst == "HH" and h.art in OPEN_HAT for h in hits):
                problems.append(f"{where}: an open hi-hat struck while the pedal closes it")
            sticking = [h for h in hits if h.inst == STICKING_ROW]
            if sticking and not hands:
                problems.append(f"{where}: sticking '{sticking[0].art}' where no hand plays")
    return problems
