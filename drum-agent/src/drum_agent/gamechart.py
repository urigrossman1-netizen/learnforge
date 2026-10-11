"""Read a rhythm-game drum chart (Rock Band / Clone Hero `notes.mid`, or a Clone Hero
`.chart`) as evidence for a transcription: form, tempo map, bar times and the drum
lanes of every bar, printed as a text grid you can compare with your chart.

Game charts are beat-mapped to the master recording, so they are excellent for the
tempo map, section markers, bar counts and rhythms. Their lanes are a game
simplification: one pad per colour, cymbal choice by lane, flams often shown as two
pads at once, no hi-hat openings except in the drummer-animation track. Use them as
evidence alongside lessons and your ears; write the chart in your own notation and
never copy or redistribute the game files.

    drum-agent game-chart notes.mid                      # form summary + every bar
    drum-agent game-chart notes.mid --bars 20-36         # some bars
    drum-agent game-chart notes.mid --form               # form summary only
    drum-agent game-chart notes.mid --anim --bars 47-48  # drummer animation (hands, crash 1/2, hi-hat open)
    drum-agent game-chart song.chart --offset -4.0       # shift times (game audio lead-in) to album time

Lanes (4-lane pro drums): KICK, SNARE, then cymbals Y=hi-hat, B=ride, G=crash and toms
Y=high, B=mid, G=floor. Charters re-use lanes: a second crash often sits on the yellow
or blue cymbal in crash-heavy sections, and in some songs the blue cymbal is an open
hi-hat. Check the animation track (--anim, .mid only) when the lane is ambiguous.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from bisect import bisect_right
from typing import Dict, List, Tuple

ROWS = ["G-CYM", "B-CYM", "Y-CYM", "Y-TOM", "B-TOM", "SNARE", "G-TOM", "KICK"]
HINT = {"G-CYM": "crash", "B-CYM": "ride", "Y-CYM": "hi-hat", "Y-TOM": "hi tom", "B-TOM": "mid tom",
        "G-TOM": "floor", "SNARE": "snare", "KICK": "kick"}
ANIM = {24: "kick", 25: "hh-open", 26: "snare-L", 27: "snare-R", 28: "snare-L(soft)", 29: "snare-R(soft)",
        30: "hihat-L", 31: "hihat-R", 32: "perc-R", 34: "crash1-L", 35: "crash1-L(soft)", 36: "crash1-R",
        37: "crash1-R(soft)", 38: "crash2-R", 39: "crash2-R(soft)", 40: "crash1-choke", 41: "crash2-choke",
        42: "ride-R", 43: "ride-L", 44: "crash2-L", 45: "crash2-L(soft)", 46: "tom1-L", 47: "tom1-R",
        48: "tom2-L", 49: "tom2-R", 50: "floor-L", 51: "floor-R"}
SUBDIV = [1, 2, 3, 4, 6, 8, 12]


class Song:
    def __init__(self):
        self.res = 480                       # ticks per beat
        self.tempos: List[Tuple[int, float]] = [(0, 120.0)]       # (tick, bpm)
        self.sigs: List[Tuple[int, int, int]] = [(0, 4, 4)]       # (tick, num, den)
        self.events: List[Tuple[int, str]] = []                   # (tick, text)
        self.hits: List[Tuple[int, str, str]] = []                # (tick, row, mark)  mark: x X(accent) g(ghost) f(flam)
        self.anim: List[Tuple[int, str]] = []
        self.marks: List[Tuple[int, str]] = []                    # music_start / music_end / end

    # ---- time helpers
    def seconds(self, tick: int) -> float:
        t, s, bpm = 0, 0.0, self.tempos[0][1]
        for tk, b in self.tempos:
            if tk > tick:
                break
            s += (tk - t) / self.res * 60.0 / bpm
            t, bpm = tk, b
        return s + (tick - t) / self.res * 60.0 / bpm

    def bars(self, end: int) -> List[Tuple[int, int, int]]:
        """(start tick, beats, beat ticks) for every bar up to `end`."""
        out, t, i = [], 0, 0
        while t <= end:
            while i + 1 < len(self.sigs) and self.sigs[i + 1][0] <= t:
                i += 1
            _, num, den = self.sigs[i]
            beat = self.res * 4 // den
            out.append((t, num, beat))
            t += num * beat
        return out


# --------------------------------------------------------------------------
def load_mid(path: str) -> Song:
    import mido
    m = mido.MidiFile(path)
    s = Song()
    s.res = m.ticks_per_beat
    s.tempos, s.sigs = [], []
    tracks = {}
    for tr in m.tracks:
        name = next((x.name for x in tr if x.type == "track_name"), "")
        t, ev = 0, []
        for x in tr:
            t += x.time
            ev.append((t, x))
        tracks[name] = ev
        for tk, x in ev:
            if x.type == "set_tempo":
                s.tempos.append((tk, 60_000_000 / x.tempo))
            elif x.type == "time_signature":
                s.sigs.append((tk, x.numerator, x.denominator))
    s.tempos = sorted(s.tempos) or [(0, 120.0)]
    s.sigs = sorted(s.sigs) or [(0, 4, 4)]
    for tk, x in tracks.get("EVENTS", []):
        if x.type in ("text", "marker"):
            txt = x.text.strip("[]")
            if txt.startswith("section ") or txt.startswith("prc_"):
                s.events.append((tk, txt.replace("section ", "")))
            elif txt in ("music_start", "music_end", "end"):
                s.marks.append((tk, txt))
    dr = tracks.get("PART DRUMS") or tracks.get("PART REAL_DRUMS_PS") or []
    dynamics = any(x.type == "text" and "ENABLE_CHART_DYNAMICS" in x.text for _, x in dr)
    ons = [(tk, x.note, x.velocity) for tk, x in dr if x.type == "note_on" and x.velocity > 0]
    spans: Dict[int, List[Tuple[int, int]]] = {110: [], 111: [], 112: [], 109: []}
    open_: Dict[int, int] = {}
    for tk, x in dr:
        if x.type in ("note_on", "note_off") and x.note in spans:
            if x.type == "note_on" and x.velocity > 0:
                open_[x.note] = tk
            elif x.note in open_:
                spans[x.note].append((open_.pop(x.note), tk))

    def inside(n, tk):
        return any(a <= tk < b for a, b in spans[n])

    for tk, n, vel in ons:
        mark = "x"
        if dynamics and n in (97, 98, 99, 100):
            mark = "X" if vel == 127 else ("g" if vel == 1 else "x")
        if n in (96, 95):
            row = "KICK"
        elif n == 97:
            row = "SNARE"
        elif n == 98:
            row = "Y-TOM" if inside(110, tk) else "Y-CYM"
        elif n == 99:
            row = "B-TOM" if inside(111, tk) else "B-CYM"
        elif n == 100:
            row = "G-TOM" if inside(112, tk) else "G-CYM"
        else:
            if n in ANIM:
                s.anim.append((tk, ANIM[n]))
            continue
        if inside(109, tk) and row != "KICK":
            mark = "f"
        s.hits.append((tk, row, mark))
    return s


def load_chart(path: str) -> Song:
    s = Song()
    s.tempos, s.sigs = [], []
    sec, text = None, open(path, encoding="utf-8-sig", errors="replace").read()
    notes: Dict[int, List[int]] = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            sec = line.strip("[]")
            continue
        mm = re.match(r"(\d+)\s*=\s*(\w+)\s*(.*)", line)
        if not mm:
            mm2 = re.match(r'Resolution\s*=\s*(\d+)', line)
            if mm2 and sec == "Song":
                s.res = int(mm2.group(1))
            continue
        tk, kind, rest = int(mm.group(1)), mm.group(2), mm.group(3)
        if sec == "SyncTrack":
            if kind == "B":
                s.tempos.append((tk, int(rest.split()[0]) / 1000.0))
            elif kind == "TS":
                p = rest.split()
                s.sigs.append((tk, int(p[0]), 2 ** int(p[1]) if len(p) > 1 else 4))
        elif sec == "Events" and kind == "E":
            txt = rest.strip('"')
            if txt.startswith("section "):
                s.events.append((tk, txt.replace("section ", "")))
            elif txt == "end":
                s.marks.append((tk, txt))
        elif sec == "ExpertDrums" and kind == "N":
            notes.setdefault(tk, []).append(int(rest.split()[0]))
    s.tempos = sorted(s.tempos) or [(0, 120.0)]
    s.sigs = sorted(s.sigs) or [(0, 4, 4)]
    for tk, ns in notes.items():
        for n in ns:
            if n in (0, 32):
                row = "KICK"
            elif n == 1:
                row = "SNARE"
            elif n in (2, 3, 4):
                col = "YBG"[n - 2]
                row = f"{col}-CYM" if (64 + n) in ns else f"{col}-TOM"
            else:
                continue
            mark = "X" if (33 + n) in ns and n in (1, 2, 3, 4) else ("g" if (39 + n) in ns and n in (1, 2, 3, 4) else "x")
            s.hits.append((tk, row, mark))
    return s


# --------------------------------------------------------------------------
def grid_for_bar(hits, start, beats, beat_ticks) -> Dict[str, str]:
    """Rows of .drums-style beat groups for one bar (coarsest subdivision per beat)."""
    q = 24
    pos: Dict[int, Dict[int, Dict[str, str]]] = {}
    for tk, row, mark in hits:
        rel = (tk - start) / beat_ticks
        b = math.floor(rel + 1e-6)
        k = round((rel - b) * q)
        if k == q:
            b, k = b + 1, 0
        if 0 <= b < beats:
            pos.setdefault(b, {}).setdefault(k, {})[row] = mark
    rows: Dict[str, List[str]] = {r: [] for r in ROWS}
    for b in range(beats):
        ks = pos.get(b, {})
        n = next((d for d in SUBDIV if all(k % (q // d) == 0 for k in ks)), q)
        for r in ROWS:
            cells = ["-"] * n
            for k, rr in ks.items():
                if r in rr:
                    cells[k * n // q] = rr[r]
            rows[r].append("".join(cells))
    return {r: " ".join(v) for r, v in rows.items() if any(c != "-" for c in "".join(v).replace(" ", ""))}


def fmt_t(sec: float) -> str:
    sign = "-" if sec < 0 else ""
    sec = abs(sec)
    return f"{sign}{int(sec // 60)}:{sec % 60:05.2f}"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="drum-agent game-chart", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--bars", default="", help="range like 20-36 (1-based, as printed)")
    ap.add_argument("--form", action="store_true", help="only the form / tempo summary")
    ap.add_argument("--anim", action="store_true", help="print the drummer-animation track instead of lanes (.mid)")
    ap.add_argument("--offset", type=float, default=0.0, help="seconds added to every time (e.g. -4.0 for a game lead-in)")
    a = ap.parse_args(argv)
    s = load_mid(a.file) if a.file.lower().endswith((".mid", ".midi")) else load_chart(a.file)
    if not s.hits:
        sys.exit("no expert drum notes found")
    end = max(t for t, _, _ in s.hits)
    bars = s.bars(end)
    starts = [b[0] for b in bars]

    def bar_of(tk):
        return bisect_right(starts, tk)          # 1-based

    def bpm_at(tk):
        i = bisect_right([t for t, _ in s.tempos], tk) - 1
        return s.tempos[max(i, 0)][1]

    first_hit = min(t for t, _, _ in s.hits)
    # ---- form summary
    print(f"{a.file}: {len(bars)} bars, first drum hit in bar {bar_of(first_hit)} at "
          f"{fmt_t(s.seconds(first_hit) + a.offset)}, last at {fmt_t(s.seconds(end) + a.offset)}"
          + (f" (times shifted {a.offset:+.2f} s)" if a.offset else ""))
    for t, name in s.marks:
        print(f"  [{name}] bar {bar_of(t)} at {fmt_t(s.seconds(t) + a.offset)}")
    secs = [(bar_of(t), name, t) for t, name in s.events if not name.startswith("prc_")] or []
    if secs:
        print(f"\n{'section':<22} {'bars':>9} {'count':>5} {'start':>9} {'avg bpm':>8}")
        for i, (b0, name, tk) in enumerate(secs):
            b1 = secs[i + 1][0] - 1 if i + 1 < len(secs) else len(bars)
            t0 = starts[b0 - 1]
            t1 = starts[b1] if b1 < len(starts) else (bars[-1][0] + bars[-1][1] * bars[-1][2])
            dur = s.seconds(t1) - s.seconds(t0)
            beats_n = sum(bars[k][1] * bars[k][2] for k in range(b0 - 1, min(b1, len(bars)))) / s.res
            avg = beats_n / dur * 60 if dur > 0 else 0
            print(f"{name[:22]:<22} {b0:>4}-{b1:<4} {b1 - b0 + 1:>5} {fmt_t(s.seconds(t0) + a.offset):>9} {avg:>8.1f}")
    odd = [(i + 1, n) for i, (_, n, _) in enumerate(bars) if n != 4]
    if odd:
        print("\nbars not in 4: " + ", ".join(f"{b} ({n} beats)" for b, n in odd))
    if a.form:
        return

    lo, hi = 1, len(bars)
    if a.bars:
        p = a.bars.split("-")
        lo, hi = int(p[0]), int(p[-1])
    print()
    for i in range(lo - 1, min(hi, len(bars))):
        t0, beats, bt = bars[i]
        names = [n for t, n in s.events + s.marks if t0 <= t < t0 + beats * bt]
        head = f"bar {i + 1:>4}  {fmt_t(s.seconds(t0) + a.offset)}  {bpm_at(t0):6.1f} bpm"
        if beats != 4:
            head += f"  [{beats} beats]"
        if names:
            head += "  [" + "] [".join(names) + "]"
        print(head)
        if a.anim:
            ev: Dict[float, List[str]] = {}
            for tk, nm in s.anim:
                if t0 <= tk < t0 + beats * bt:
                    ev.setdefault(round((tk - t0) / bt, 3), []).append(nm)
            print("   " + "  ".join(f"{1 + p:.2f}:{'+'.join(v)}" for p, v in sorted(ev.items())))
            continue
        for row, cells in grid_for_bar(s.hits, t0, beats, bt).items():
            print(f"   {row:<6} {cells}    ({HINT[row]})")


if __name__ == "__main__":
    main()
