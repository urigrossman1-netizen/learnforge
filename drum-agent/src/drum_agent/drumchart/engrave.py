"""Layout + SVG engraving.

All coordinates are in staff spaces (sp); the staff's top line is y = 0 and its
bottom line y = 4.  Each system is emitted as an HTML header row (section box,
tempo) plus three aligned SVGs (staff, counts, grid) sharing x coordinates.

Layout model ("4-cell grid", see references/engraving.md):
  * every section starts a new system; a system holds `per_line` equal cells
  * a bar fills one cell (dense bars - 32nds, sextuplets, flams in 16ths - take two)
  * so barlines line up vertically down the page
  * inside a bar every beat gets equal width and slots are spaced uniformly,
    so the count grid sits exactly under the notes
Vertical lanes above the staff, outermost first: section box + tempo (HTML),
cue text, dynamics/hairpins, fermatas, then accents and hi-hat o/+ marks.
"""
from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass, field
from fractions import Fraction as Fr
from typing import Dict, List, Optional, Tuple

from .model import INSTRUMENTS, STAFF_STYLE, STICKING_ROW, Bar, Chart, Meter
from .notation import VoiceBar, engrave_bar

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
with open(os.path.join(ASSETS, "bravura_glyphs.json"), encoding="utf-8") as _fh:
    _G = json.load(_fh)
GLYPHS = _G["glyphs"]
ED = _G["engravingDefaults"]

# --- engraving constants (staff spaces, Bravura engravingDefaults) ---------
STAFF_LINE = ED["staffLineThickness"]       # 0.13
STEM = ED["stemThickness"]                  # 0.12
BEAM = ED["beamThickness"]                  # 0.5
BEAM_GAP = ED["beamSpacing"]                # 0.25
BEAM_STEP = BEAM + BEAM_GAP                 # 0.75
LEDGER = ED["legerLineThickness"]           # 0.16
LEDGER_EXT = ED["legerLineExtension"]       # 0.4
THIN_BAR = ED["thinBarlineThickness"]       # 0.16
THICK_BAR = ED["thickBarlineThickness"]     # 0.5
BAR_SEP = ED["barlineSeparation"]           # 0.4
HAIRPIN = ED["hairpinThickness"]            # 0.16
STEM_LEN = 3.5
BEAM_CLEAR = 3.25        # stem length from the outermost note to a flat beam

GUTTER = 7.0             # left gutter (grid labels); the staff starts here
CLEF_W = 3.6             # system header: percussion clef
PAD_L = 0.85             # inside a bar: barline -> first notehead edge ~1.25 sp
PAD_R = 0.25             # ... and after the last slot
NOTE_OFF = 0.95          # notehead centre offset from the start of its time slot
HEAD_HALF = 0.6          # half a black notehead (stem side)
MIN_GAP_R = 1.3          # last notehead edge -> barline, at least
MIN_SQUEEZE = 0.88       # dense bars may be spaced down to this before a line is split
MIN_SQUEEZE_1 = 0.92     # a single-bar line squeezes only this far; the page scales a wider one down to fit
NOTE_OFF_GRACE = 2.05    # ... when the beat contains flams/drags
MIN_SLOT = 1.55          # minimum spacing between adjacent slots (1-cell bars)
MIN_SLOT_GRACE = 2.7
GRID_ROW = 1.75
COUNT_H = 2.3
STICK_H = 1.9

FAMILY_CLASS = {"crash": "cym", "ride": "cym", "hat": "cym", "snare": "snr", "tom": "tom",
                "kick": "kik", "foot": "neu", "perc": "neu"}


def f(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def gw(name: str) -> float:
    g = GLYPHS[name]
    return g["bbox"][2] - g["bbox"][0] if g["bbox"] else g["adv"]


def head_width(name: str) -> float:
    return GLYPHS[name]["adv"] or gw(name)


def anchor(name: str, key: str, default: Tuple[float, float]) -> Tuple[float, float]:
    a = GLYPHS[name]["anchors"].get(key)
    return (a[0], a[1]) if a else default


def use(name: str, x: float, y: float, scale: float = 1.0, cls: str = "") -> str:
    c = f' class="{cls}"' if cls else ""
    if scale == 1.0:
        return f'<use href="#g-{name}" x="{f(x)}" y="{f(y)}"{c}/>'
    return f'<use href="#g-{name}" transform="translate({f(x)} {f(y)}) scale({f(scale)})"{c}/>'


def glyph_defs() -> str:
    return "".join(f'<path id="g-{n}" d="{g["d"]}"/>' for n, g in GLYPHS.items())


def ypos(p: int) -> float:
    return (8 - p) / 2.0


def text_w(s: str, size: float, k: float = 0.52) -> float:
    """Rough advance width of a text run (used only for collision avoidance)."""
    return len(s) * size * k


# --------------------------------------------------------------------------
# Counting labels
# --------------------------------------------------------------------------
def count_labels(meter: Meter, g: int, n: int, mode: str = "") -> List[Tuple[str, bool]]:
    """[(label, is_beat_number)] for the n slots of group g.
    4/4: 1 e & a / 1 & / 1 trip let;  6/8 & 9/8: 1 2 3 4 5 6;  12/8: 1 & a 2 & a ..."""
    D = meter.groups[g]
    eighth = Fr(1, 8)
    by_eighths = meter.den == 8 and (mode == "eighths" or (mode != "beats" and meter.num != 12))
    if by_eighths:
        start = int(sum(meter.groups[:g]) / eighth) + 1
        k = int(D / eighth)
        if n % k == 0:
            per = n // k
            sub = {1: [], 2: ["&"], 4: ["e", "&", "a"]}.get(per, ["·"] * (per - 1))
            out = []
            for j in range(k):
                out.append((str(start + j), j == 0))
                out.extend((s, False) for s in sub)
            return out
        return [(str(start), True)] + [("·", False)] * (n - 1)
    beat = str(g + 1)
    if meter.compound or (meter.num == 12 and meter.den == 8):
        table = {1: [], 2: ["·"], 3: ["&", "a"], 6: ["e", "&", "e", "a", "e"], 12: ["·"] * 11}
    else:
        table = {1: [], 2: ["&"], 3: ["trip", "let"], 4: ["e", "&", "a"], 6: ["la", "li", "&", "la", "li"],
                 8: ["·", "e", "·", "&", "·", "a", "·"]}
    sub = table.get(n, ["·"] * (n - 1))
    return [(beat, True)] + [(s, False) for s in sub]


# --------------------------------------------------------------------------
# Layout structures
# --------------------------------------------------------------------------
@dataclass
class BarLayout:
    bar: Bar
    vb: VoiceBar
    x: float = 0.0
    w: float = 0.0
    cells: int = 1
    prefix: float = 0.0              # width of clef/time signature at bar start
    show_clef: bool = False
    show_time: bool = False
    group_x: List[float] = field(default_factory=list)
    group_w: List[float] = field(default_factory=list)
    note_off: List[float] = field(default_factory=list)
    sec_index: int = 0               # 1-based position of this bar within its section
    first_in_section: bool = False
    last_in_section: bool = False

    def slot_x(self, g: int, k: int, n: int) -> float:
        return self.group_x[g] + self.group_w[g] * k / n + self.note_off[g]

    @property
    def body_x0(self) -> float:
        return self.x + self.prefix

    @property
    def x1(self) -> float:
        return self.x + self.w


@dataclass
class SystemLayout:
    bars: List[BarLayout]
    width: float
    section_start: bool
    index: int
    carry: List[Tuple[str, int]] = field(default_factory=list)   # hairpins continued from the line above


def _has_grace(bar: Bar, g: int) -> bool:
    return any(h.group == g and h.art in "fFd" for h in bar.hits)


def _needed_body(bar: Bar) -> float:
    """Minimum body width for the bar's busiest beat (beats get width in proportion to duration)."""
    if bar.simile or bar.rest_bars or bar.is_empty:
        return 0.0
    sizes = bar.group_sizes()
    L = float(bar.meter.length)
    need = 0.0
    for g, D in enumerate(bar.meter.groups):
        ms = MIN_SLOT_GRACE if _has_grace(bar, g) else MIN_SLOT
        extra = NOTE_OFF_GRACE - NOTE_OFF if _has_grace(bar, g) else 0
        need = max(need, (sizes[g] * ms + extra) / (float(D) / L))
    return need + PAD_L + PAD_R


def time_sig_width(m: Meter) -> float:
    def w(num: int) -> float:
        return sum(GLYPHS[f"timeSig{d}"]["adv"] for d in str(num))
    return max(w(m.num), w(m.den)) + 1.4


def compute_simile(bars: List[BarLayout], restate_each_system: bool, system_starts: set):
    """Mark one-bar (1) and two-bar (2 = first half, 3 = second half) repeats.
    A repeat sign always refers to the written-out bar(s) right before it."""
    for b in bars:
        b.bar.simile = 0
    for i, bl in enumerate(bars):
        bar = bl.bar
        if i == 0 or bl.first_in_section or bar.rest_bars or bar.is_empty or bar.has_directive("nosimile"):
            continue
        if restate_each_system and i in system_starts:
            continue
        prev = bars[i - 1].bar
        if prev.rest_bars or prev.is_empty:
            continue
        if bar.signature() == prev.signature():
            bar.simile = 1
    i = 2
    while i + 1 < len(bars):
        a, b = bars[i], bars[i + 1]
        ok = (not a.first_in_section and not b.first_in_section
              and bars[i - 2].bar.section is a.bar.section
              and a.bar.simile == 0 and b.bar.simile == 0
              and not (restate_each_system and (i in system_starts or (i + 1) in system_starts))
              and (i + 1) not in system_starts
              and a.bar.signature() == bars[i - 2].bar.signature()
              and b.bar.signature() == bars[i - 1].bar.signature()
              and a.bar.signature() != b.bar.signature()
              and not a.bar.rest_bars and not b.bar.rest_bars and not a.bar.is_empty and not b.bar.is_empty
              and bars[i - 2].bar.simile in (0, 2) and bars[i - 1].bar.simile in (0, 3)
              and not a.bar.has_directive("nosimile") and not b.bar.has_directive("nosimile"))
        if ok:
            a.bar.simile, b.bar.simile = 2, 3
            i += 2
            continue
        i += 1


def layout_chart(chart: Chart, per_line: int, content_width: float) -> List[SystemLayout]:
    restate = chart.meta.get("restate", "section").lower() == "system"
    cell = (content_width - CLEF_W) / per_line
    hh: Dict[str, bool] = {}
    all_bl: List[BarLayout] = []
    for sec in chart.sections:
        for j, bar in enumerate(sec.bars):
            all_bl.append(BarLayout(bar=bar, vb=engrave_bar(bar, hh), sec_index=j + 1,
                                    first_in_section=(j == 0), last_in_section=(j == len(sec.bars) - 1)))
    # systems: per_line bars (a phrase) per line; sections always start a new line.
    # A line too dense to fit even when compressed is split in two (forced breaks).
    light_w = max(0.62 * cell, 10.0)
    forced: set = set()
    for _attempt in range(6):
        systems_idx: List[List[int]] = []
        cur: List[int] = []
        cur_sec = None
        cap = per_line
        for i, bl in enumerate(all_bl):
            sec = bl.bar.section
            new_sec = sec is not cur_sec
            if new_sec:
                want = sec.per_line or int(chart.meta.get("per-line", per_line) or per_line)
                cap = max(1, min(per_line, want))
            if cur and (new_sec or len(cur) >= cap or bl.bar.has_directive("break") or i in forced):
                systems_idx.append(cur)
                cur = []
            cur_sec = sec
            cur.append(i)
        if cur:
            systems_idx.append(cur)
        starts = {s[0] for s in systems_idx}
        compute_simile(all_bl, restate, starts)

        # bar widths: one cell each, so barlines align down the page.  A dense bar (flams in
        # 16ths, 32nds, sextuplets) borrows room from light bars (repeat signs, rests), then
        # from ordinary bars in its own line, then the dense bars are spaced a little tighter,
        # so the phrase stays on one line at the page width.
        split = False
        prev_meter = None
        for idxs in systems_idx:
            bls = [all_bl[i] for i in idxs]
            m0 = bls[0].bar.meter
            ts_w = time_sig_width(m0) if (prev_meter is None or m0 != prev_meter) else 0.0
            prev_meter = bls[-1].bar.meter
            need = [_needed_body(bl.bar) for bl in bls]
            light = [bool(bl.bar.simile or bl.bar.rest_bars or bl.bar.is_empty) for bl in bls]
            w = [max(cell, n) for n in need]
            full = len(bls) == per_line or any(i in forced for i in idxs) or (idxs[-1] + 1) in forced
            budget = cell * (per_line if full else len(bls)) - ts_w
            if per_line > 1:
                over = sum(w) - budget
                for k in range(len(bls)):
                    if light[k] and over > 0:
                        d = min(w[k] - light_w, over)
                        w[k] -= d
                        over -= d
                for k in range(len(bls)):
                    if not light[k] and need[k] <= cell and over > 0:
                        d = min(w[k] - max(need[k], 0.8 * cell), over)
                        if d > 0:
                            w[k] -= d
                            over -= d
            over = sum(w) - budget
            if over > 0.01:
                # share the room among the written bars in proportion to what each needs
                room = budget - sum(ww for ww, lt in zip(w, light) if lt)
                needs = [max(n, 0.7 * cell) for n in need]   # ordinary bars keep room for ledger lines and chords
                tot_need = sum(n for n, lt in zip(needs, light) if not lt)
                factor = room / tot_need if tot_need else 1.0
                if factor < MIN_SQUEEZE and len(bls) > 1:
                    forced.add(idxs[len(idxs) // 2])
                    split = True
                if factor >= 1.0:       # every bar gets its need; the rest goes to bars that wanted a full cell
                    want = [max(0.0, ww - n) for ww, n in zip(w, needs)]
                    tw = sum(x for x, lt in zip(want, light) if not lt) or 1.0
                    slack = room - tot_need
                    w = [ww if lt else n + slack * x / tw for ww, n, x, lt in zip(w, needs, want, light)]
                else:
                    factor = max(factor, MIN_SQUEEZE_1)
                    w = [ww if lt else n * factor for ww, n, lt in zip(w, needs, light)]
            if full and len(bls) < per_line and sum(w) < budget - 0.01:
                w = [ww * budget / sum(w) for ww in w]      # a line split for density spans the page
            for bl, ww in zip(bls, w):
                bl.body_w = ww  # type: ignore[attr-defined]
        if not split:
            break

    out: List[SystemLayout] = []
    prev_meter = None
    for si, idxs in enumerate(systems_idx):
        bls = [all_bl[i] for i in idxs]
        x = GUTTER
        for k, bl in enumerate(bls):
            bar = bl.bar
            bl.show_clef = k == 0
            bl.show_time = prev_meter is None or bar.meter != prev_meter
            prev_meter = bar.meter
            bl.prefix = (CLEF_W if bl.show_clef else 0) + (time_sig_width(bar.meter) if bl.show_time else 0)
            body = bl.body_w  # type: ignore[attr-defined]
            bl.x = x
            bl.w = bl.prefix + body
            L = float(bar.meter.length)
            sizes = bar.group_sizes()
            # last played slot: keep its notehead and stem clear of the barline
            gl = len(bar.meter.groups) - 1
            last_k = max((h.slot for h in bar.hits if h.group == gl and h.inst != "ST"), default=-1)
            pad_r = PAD_R
            for _ in range(3):
                inner = body - PAD_L - pad_r
                gx = x + bl.prefix + PAD_L
                bl.group_x, bl.group_w, bl.note_off = [], [], []
                for g, D in enumerate(bar.meter.groups):
                    w = inner * float(D) / L
                    bl.group_x.append(gx)
                    bl.group_w.append(w)
                    bl.note_off.append(NOTE_OFF_GRACE if _has_grace(bar, g)
                                       else min(NOTE_OFF, max(0.75, w / max(1, sizes[g]) * 0.62)))
                    gx += w
                if last_k < 0 or bar.simile or bar.rest_bars:
                    break
                bar_in = (THIN_BAR + BAR_SEP + THICK_BAR) if bl.last_in_section else THIN_BAR
                gap = (x + bl.w - bar_in) - (bl.slot_x(gl, last_k, sizes[gl]) + HEAD_HALF)
                if gap >= MIN_GAP_R - 1e-6:
                    break
                pad_r += MIN_GAP_R - gap
            x += bl.w
        out.append(SystemLayout(bls, x, bls[0].first_in_section, si))
    # a hairpin longer than the rest of its line continues at the start of the next line
    for si, sl in enumerate(out):
        pending = list(sl.carry)
        for bi, bl in enumerate(sl.bars):
            for d in bl.bar.directives:
                if d.kind in ("cresc", "dim"):
                    nb = int(d.opts.get("bars", d.args[0] if d.args and d.args[0].isdigit() else "1"))
                    pending.append((d.kind, nb - (len(sl.bars) - bi)))
        if si + 1 < len(out):
            out[si + 1].carry = [(k, r) for k, r in pending if r > 0]
    return out


# --------------------------------------------------------------------------
# SVG canvas
# --------------------------------------------------------------------------
class Canvas:
    def __init__(self):
        self.items: List[str] = []
        self.ymin = 0.0
        self.ymax = 4.0

    def add(self, s: str, y0: float, y1: float):
        self.items.append(s)
        self.ymin = min(self.ymin, y0)
        self.ymax = max(self.ymax, y1)

    def merge(self, other: "Canvas"):
        self.items.extend(other.items)
        self.ymin = min(self.ymin, other.ymin)
        self.ymax = max(self.ymax, other.ymax)

    def glyph(self, name: str, x: float, y: float, scale: float = 1.0, cls: str = ""):
        bb = GLYPHS[name]["bbox"] or [0, -0.5, 1, 0.5]
        self.add(use(name, x, y, scale, cls), y + bb[1] * scale, y + bb[3] * scale)

    def rect(self, x, y, w, h, cls="", extra=""):
        c = f' class="{cls}"' if cls else ""
        self.add(f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}"{c}{extra}/>', y, y + h)

    def line(self, x1, y1, x2, y2, sw, cls=""):
        c = f' class="{cls}"' if cls else ""
        self.add(f'<line x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}" stroke-width="{f(sw)}"{c}/>',
                 min(y1, y2) - sw / 2, max(y1, y2) + sw / 2)

    def text(self, x, y, s, size, cls="", anchor="start", extra=""):
        a = "" if anchor == "start" else f' text-anchor="{anchor}"'
        c = f' class="{cls}"' if cls else ""
        self.add(f'<text x="{f(x)}" y="{f(y)}" font-size="{f(size)}"{a}{c}{extra}>{esc(s)}</text>',
                 y - size * 0.8, y + size * 0.25)


@dataclass
class ChordGeom:
    x_on: float
    stem_x: float          # outer edge of the stem (right edge for up, left edge for down)
    stem_end: float
    stem_start: float
    heads: List[Tuple[object, float, float]]   # (NoteHead, x_left, y)


# --------------------------------------------------------------------------
# One bar of notation
# --------------------------------------------------------------------------
def compute_beam_heights(bl: BarLayout) -> Dict[str, Optional[float]]:
    """Flat beams at one height per voice per bar: 3.25 sp beyond the outermost beamed note."""
    out: Dict[str, Optional[float]] = {"up": None, "down": None}
    vb = bl.vb
    for voice in ("up", "down"):
        ys = []
        maxlvl = 1
        for bm in vb.beams:
            if bm.voice != voice:
                continue
            for i in bm.elems:
                e = vb.elems[i]
                if e.kind == "chord":
                    ps = [ypos(n.pos) for n in e.notes]
                    ys.append(min(ps) if voice == "up" else max(ps))
                    maxlvl = max(maxlvl, e.flags)
        if not ys:
            continue
        extra = max(0, maxlvl - 2) * BEAM_STEP
        if voice == "up":
            out["up"] = min(min(ys) - BEAM_CLEAR - extra, -1.75)
        else:
            out["down"] = max(max(ys) + BEAM_CLEAR + extra, 5.75)
    return out


def draw_bar_notation(cv: Canvas, bl: BarLayout) -> None:
    vb = bl.vb
    beam_y = compute_beam_heights(bl)
    geoms: Dict[int, ChordGeom] = {}

    # ---------- chords: noteheads, ledger lines, stems, flags ----------
    for i, e in enumerate(vb.elems):
        if e.kind != "chord":
            continue
        x_on = bl.slot_x(e.group, e.slot, e.nslots)
        up = e.voice == "up"
        stem_x = x_on + 0.59 if up else x_on - 0.59
        heads = []
        for nh in e.notes:
            hw = head_width(nh.head)
            y = ypos(nh.pos)
            if up:
                ax, _ = anchor(nh.head, "stemUpSE", (hw, -0.168))
                xl = stem_x - ax if nh.shift == 0 else stem_x
            else:
                ax, _ = anchor(nh.head, "stemDownNW", (0.0, 0.168))
                xl = stem_x - ax if nh.shift == 0 else stem_x - hw
            heads.append((nh, xl, y))
        ys = [h[2] for h in heads]
        top_y, bot_y = min(ys), max(ys)
        if up:
            far = max(heads, key=lambda h: h[2])
            _, ay = anchor(far[0].head, "stemUpSE", (0, -0.168))
            start = far[2] + ay
            if e.beam is not None and beam_y["up"] is not None:
                end = beam_y["up"]
            else:
                end = top_y - STEM_LEN - (0.25 if e.flags == 2 else 0.75 if e.flags >= 3 else 0)
        else:
            far = min(heads, key=lambda h: h[2])
            _, ay = anchor(far[0].head, "stemDownNW", (0, 0.168))
            start = far[2] + ay
            if e.beam is not None and beam_y["down"] is not None:
                end = beam_y["down"]
            else:
                end = bot_y + STEM_LEN + (0.25 if e.flags == 2 else 0.75 if e.flags >= 3 else 0)
        geoms[i] = ChordGeom(x_on, stem_x, end, start, heads)

        maxr = max(xl + head_width(nh.head) for nh, xl, _ in heads)
        for nh, xl, y in heads:
            hw = head_width(nh.head)
            if nh.pos >= 10:
                for lp in range(10, nh.pos + 1, 2):
                    cv.line(xl - LEDGER_EXT, ypos(lp), xl + hw + LEDGER_EXT, ypos(lp), LEDGER, "ink-stroke")
            if nh.pos <= -2:
                for lp in range(-2, nh.pos - 1, -2):
                    cv.line(xl - LEDGER_EXT, ypos(lp), xl + hw + LEDGER_EXT, ypos(lp), LEDGER, "ink-stroke")
            cv.glyph(nh.head, xl, y)
            if nh.ghost:
                cv.glyph("noteheadParenthesisLeft", xl - 0.332 - 0.05, y)
                cv.glyph("noteheadParenthesisRight", xl + hw + 0.028 + 0.05, y)
            if nh.choke and STAFF_STYLE["choke"] == "pict":
                cv.glyph("pictChokeCymbal", xl + hw + 0.15, y - 0.35)
            if nh.flam or nh.drag:
                _grace(cv, nh, xl, y, drag=nh.drag)
            for _ in range(e.dots):
                dy = y if nh.pos % 2 == 1 else (y - 0.5 if up else y + 0.5)
                cv.glyph("augmentationDot", maxr + 0.3, dy)
        sx = stem_x - STEM if up else stem_x
        y0, y1 = sorted((start, end))
        cv.rect(sx, y0, STEM, y1 - y0, "ink")
        if STAFF_STYLE["choke"] == "dot" and any(nh.choke for nh, _, _ in heads):
            # Drum Key: a choked cymbal is an X with a dot beyond the end of the stem
            dw = gw("articStaccatoAbove")
            cx = stem_x - STEM / 2 if up else stem_x + STEM / 2
            cv.glyph("articStaccatoAbove", cx - dw / 2, (y0 - 0.45) if up else (y1 + 0.75))
        if any(nh.buzz for nh, _, _ in heads):
            bwid = gw("buzzRoll")
            cx = stem_x - STEM / 2 if up else stem_x + STEM / 2
            cv.glyph("buzzRoll", cx - bwid / 2, (start + end) / 2 + 0.45)
        if e.beam is None and e.flags > 0:
            fl = {1: "8th", 2: "16th", 3: "32nd"}[min(e.flags, 3)]
            if up:
                cv.glyph(f"flag{fl}Up", stem_x - STEM, end)
            else:
                cv.glyph(f"flag{fl}Down", stem_x, end)

    # ---------- beams ----------
    for bm in vb.beams:
        chords = [i for i in bm.elems if vb.elems[i].kind == "chord"]
        if len(chords) < 2:
            continue
        up = bm.voice == "up"
        by = beam_y[bm.voice]
        g0, g1 = geoms[chords[0]], geoms[chords[-1]]
        xl = g0.stem_x - STEM if up else g0.stem_x
        xr = g1.stem_x if up else g1.stem_x + STEM
        cv.rect(xl, by if up else by - BEAM, xr - xl, BEAM, "ink")
        maxlvl = max(vb.elems[i].flags for i in chords)
        for lvl in range(2, maxlvl + 1):
            off = (lvl - 1) * BEAM_STEP
            yy = by + off if up else by - BEAM - off
            for j, ci in enumerate(chords):
                e = vb.elems[ci]
                if e.flags < lvl:
                    continue
                prev_ok = j > 0 and vb.elems[chords[j - 1]].flags >= lvl
                next_ok = j + 1 < len(chords) and vb.elems[chords[j + 1]].flags >= lvl
                gx = geoms[ci]
                cx_l = gx.stem_x - STEM if up else gx.stem_x
                cx_r = gx.stem_x if up else gx.stem_x + STEM
                if next_ok:
                    gn = geoms[chords[j + 1]]
                    nx_r = gn.stem_x if up else gn.stem_x + STEM
                    cv.rect(cx_l, yy, nx_r - cx_l, BEAM, "ink")
                elif not prev_ok:
                    gap = abs(geoms[chords[1]].x_on - geoms[chords[0]].x_on) if len(chords) > 1 else 2
                    stub = min(1.1, gap * 0.75)
                    if j == 0:
                        cv.rect(cx_l, yy, stub, BEAM, "ink")
                    else:
                        cv.rect(cx_r - stub, yy, stub, BEAM, "ink")

    # ---------- rests ----------
    for i, e in enumerate(vb.elems):
        if e.kind == "rest" and not e.hidden:
            name = {Fr(1, 1): "restWhole", Fr(1, 2): "restHalf", Fr(1, 4): "restQuarter", Fr(1, 8): "rest8th",
                    Fr(1, 16): "rest16th", Fr(1, 32): "rest32nd"}.get(e.value, "rest16th")
            x_on = bl.slot_x(e.group, e.slot, e.nslots)
            w = gw(name)
            bb = GLYPHS[name]["bbox"]
            if e.merged:
                y = {"restHalf": 2.0, "restWhole": 1.0}.get(name, 2.0)
            else:
                span_x1 = x_on + max(w / 2 + 0.6, bl.group_w[e.group] * e.span_slots / e.nslots - 0.4)
                others = [h[2] for j, gg in geoms.items() if vb.elems[j].voice != e.voice
                          and x_on - w / 2 - 0.8 <= gg.x_on <= span_x1 for h in gg.heads]
                if e.voice == "up":
                    y = 0.0                                   # top line (+2 sp from centre)
                    top_other = min(others) - 0.5 if others else 99
                    while y + bb[3] > top_other - 0.25 and y > -4:
                        y -= 1.0
                else:
                    y = 4.0                                   # bottom line (-2 sp from centre)
                    bot_other = max(others) + 0.5 if others else -99
                    while y + bb[1] < bot_other + 0.25 and y < 8:
                        y += 1.0
            cv.glyph(name, x_on - w / 2, y, cls="rest")
            if e.dots:
                cv.glyph("augmentationDot", x_on + w / 2 + 0.3, y - 0.5 if name not in ("rest8th", "rest16th") else y - 0.2)
        elif e.kind == "mrest":
            w = gw("restWhole")
            cv.glyph("restWhole", (bl.body_x0 + bl.x1) / 2 - w / 2, 1.0)

    # ---------- articulation lanes (one lane per voice per bar) ----------
    up_ends = [g.stem_end for j, g in geoms.items() if vb.elems[j].voice == "up"]
    dn_ends = [g.stem_end for j, g in geoms.items() if vb.elems[j].voice == "down"]
    lane_up = (min(up_ends) if up_ends else 0) - 0.45
    lane_dn = (max(dn_ends) if dn_ends else 4) + 0.45
    any_acc_up = any(nh.accent for j, g in geoms.items() if vb.elems[j].voice == "up" for nh, _, _ in g.heads)
    for i in sorted(geoms, key=lambda k: geoms[k].x_on):
        g = geoms[i]
        e = vb.elems[i]
        up = e.voice == "up"
        acc = any(nh.accent for nh, _, _ in g.heads)
        oc = None
        for nh, _, _ in g.heads:
            if nh.inst != "HH" or (not STAFF_STYLE["open_marks"] and not nh.half_mark):
                continue
            if nh.open:
                oc = "pictOpen"               # every open hat is marked: an unmarked hat reads as closed
            elif nh.half and nh.half_mark:
                oc = "pictHalfOpen2"
            elif nh.closed:
                oc = "pictOpenRimShot"
        foot_open = STAFF_STYLE["open_marks"] and any(nh.inst == "HF" and nh.open for nh, _, _ in g.heads)
        cx = g.stem_x - STEM / 2 if up else g.stem_x + STEM / 2
        if up:
            if acc:
                w = gw("articAccentAbove")
                cv.glyph("articAccentAbove", cx - w / 2, lane_up)
            if oc:
                w = gw(oc)
                cv.glyph(oc, cx - w / 2, lane_up - (1.35 if any_acc_up else 0))
        else:
            yc = lane_dn
            if acc:
                w = gw("articAccentBelow")
                bb = GLYPHS["articAccentBelow"]["bbox"]
                cv.glyph("articAccentBelow", cx - w / 2, yc - bb[1])
                yc += 1.35
            if foot_open:
                w = gw("pictOpen")
                bb = GLYPHS["pictOpen"]["bbox"]
                cv.glyph("pictOpen", cx - w / 2, yc - bb[1])

    # ---------- tuplets (number on the beam side; bracket only when not beamed) ----------
    up_tups = {(t.group, t.number) for t in vb.tuplets if t.voice == "up"}
    any_oc_up = any((nh.half_mark or (STAFF_STYLE["open_marks"] and (nh.open or nh.closed))) and nh.inst == "HH"
                    for j, g in geoms.items() if vb.elems[j].voice == "up" for nh, _, _ in g.heads)
    for t in vb.tuplets:
        if t.voice == "down" and (t.group, t.number) in up_tups and not t.partial:
            continue
        e0, e1 = vb.elems[t.first], vb.elems[t.last]
        bracket = e0.kind == "rest" or t.partial
        x0 = bl.slot_x(e0.group, e0.slot, e0.nslots) - 0.6
        x1 = bl.slot_x(e1.group, e1.slot, e1.nslots) + 0.6
        if t.first in geoms:
            x0 = geoms[t.first].x_on - 0.6
        if t.last in geoms:
            x1 = geoms[t.last].stem_x + 0.1 if e1.voice == "up" else geoms[t.last].x_on + 0.6
        digits = [f"tuplet{d}" for d in str(t.number)]
        sc = 0.78
        tw = sum(gw(d) for d in digits) * sc
        cx = (x0 + x1) / 2
        ends = [geoms[i].stem_end for i in range(t.first, t.last + 1) if i in geoms]
        if t.voice == "up":
            ytop = min(ends + [lane_up + 0.45]) if ends else lane_up
            ytop -= (1.3 if any_acc_up else 0) + (1.45 if any_oc_up else 0)
            yb = ytop - 0.5
            xx = cx - tw / 2
            for d in digits:
                cv.glyph(d, xx, yb, sc)
                xx += gw(d) * sc
            if bracket:
                yl = yb - 0.55
                cv.line(x0, yl, cx - tw / 2 - 0.3, yl, 0.16, "ink-stroke")
                cv.line(cx + tw / 2 + 0.3, yl, x1, yl, 0.16, "ink-stroke")
                cv.line(x0, yl, x0, yl + 0.6, 0.16, "ink-stroke")
                cv.line(x1, yl, x1, yl + 0.6, 0.16, "ink-stroke")
        else:
            ybot = max(ends + [lane_dn - 0.45]) if ends else lane_dn
            yb = ybot + 1.45
            xx = cx - tw / 2
            for d in digits:
                cv.glyph(d, xx, yb, sc)
                xx += gw(d) * sc
            if bracket:
                yl = yb - 0.4
                cv.line(x0, yl, cx - tw / 2 - 0.3, yl, 0.16, "ink-stroke")
                cv.line(cx + tw / 2 + 0.3, yl, x1, yl, 0.16, "ink-stroke")
                cv.line(x0, yl, x0, yl - 0.6, 0.16, "ink-stroke")
                cv.line(x1, yl, x1, yl - 0.6, 0.16, "ink-stroke")


def _grace(cv: Canvas, nh, xl: float, y: float, drag: bool):
    """Grace note(s) at 65%: slashed 8th for a flam, two beamed 16ths for a drag."""
    s = 0.65
    head = nh.head if nh.head in ("noteheadBlack", "noteheadXBlack") else "noteheadBlack"
    hw = head_width(head) * s
    xs = [xl - 1.6] if not drag else [xl - 2.5, xl - 1.5]
    if nh.ghost:
        xs = [x - 0.45 for x in xs]
    top = min(y - 2.6, 0.0)
    st = STEM * 0.85
    stems = []
    for gx in xs:
        cv.glyph(head, gx, y, s, "grace")
        sx = gx + hw
        cv.rect(sx - st, top, st, y - 0.12 - top, "ink")
        stems.append(sx)
    if not drag:
        cv.glyph("flag8thUp", stems[0] - st, top, s)
        cv.line(stems[0] - 0.65, top + 1.5, stems[0] + 0.65, top + 0.55, 0.11, "ink-stroke")
    else:
        bw = stems[1] - stems[0] + st
        cv.rect(stems[0] - st, top, bw, BEAM * s, "ink")
        cv.rect(stems[0] - st, top + BEAM_STEP * s, bw, BEAM * s, "ink")


def dynamic_glyphs(text: str) -> List[str]:
    m = {"p": "dynamicPiano", "m": "dynamicMezzo", "f": "dynamicForte", "s": "dynamicSforzando",
         "z": "dynamicZ", "r": "dynamicRinforzando", "n": "dynamicNiente"}
    return [m[c] for c in text if c in m]


def draw_time_sig(cv: Canvas, m: Meter, x: float):
    tw = time_sig_width(m)

    def row(num: int, y: float):
        ds = [f"timeSig{d}" for d in str(num)]
        wsum = sum(GLYPHS[d]["adv"] for d in ds)
        xx = x + (tw - 0.4 - wsum) / 2
        for d in ds:
            cv.glyph(d, xx, y)
            xx += GLYPHS[d]["adv"]
    row(m.num, 1.0)
    row(m.den, 3.0)


def tempo_parts(spec: str) -> Tuple[str, str, str]:
    """'117' -> ('117','q',''); '60 q. Half-time' -> ('60','q.','Half-time')."""
    parts = spec.split()
    bpm = parts[0] if parts else ""
    unit = "q"
    rest = parts[1:]
    if rest and rest[0] in ("q", "q.", "h", "h.", "e", "e."):
        unit, rest = rest[0], rest[1:]
    return bpm, unit, " ".join(rest)


def tempo_html(bpm: str, unit: str, label: str) -> str:
    """Metronome mark for the HTML header lane: [label] ♩ = bpm (glyph drawn as inline SVG)."""
    g = {"q": "metNoteQuarterUp", "h": "metNoteHalfUp", "e": "metNote8thUp"}[unit[0]]
    dotted = unit.endswith(".")
    dot = '<use href="#g-metAugmentationDot" x="1.6" y="0"/>' if dotted else ""
    note = (f'<svg class="met" viewBox="-0.1 -3.1 {2.4 if dotted else 1.5} 3.5" aria-hidden="true">'
            f'<use href="#g-{g}" x="0" y="0"/>{dot}</svg>')
    lab = f'<span class="tlabel">{esc(label)}</span>' if label else ""
    return f'<span class="tempo">{lab}{note}<span>=&#8201;{esc(bpm)}</span></span>'


# --------------------------------------------------------------------------
# Rendering a system
# --------------------------------------------------------------------------
@dataclass
class RenderedSystem:
    head_html: str
    staff_svg: str
    counts_svg: str
    grid_svg: str
    width: float
    section_id: str
    first_bar: int
    last_bar: int


def section_id(sec) -> str:
    return "sec-" + re.sub(r"[^a-z0-9]+", "-", sec.name.lower()).strip("-") + f"-{sec.line}"


def _fmt_range(a: int, b: int) -> str:
    return f"{a}" if a == b else f"{a}–{b}"


def render_system(sl: SystemLayout, chart: Chart, is_last_system: bool, first_system: bool) -> RenderedSystem:
    cv = Canvas()
    x_end = sl.width
    bars = sl.bars
    sec = bars[0].bar.section

    # ---------------- notation ----------------
    note_cv = Canvas()
    for bl in bars:
        if bl.bar.rest_bars or bl.bar.simile:
            continue
        bcv = Canvas()
        draw_bar_notation(bcv, bl)
        note_cv.merge(bcv)
    # playback highlight boxes (hidden until playing), with beat x-positions for the playhead
    for bl in bars:
        bxs = [bl.group_x[g] + bl.note_off[g] for g in range(len(bl.group_x))] + [bl.x1 - 0.2]
        nb = bl.bar.rest_bars or 1
        cv.items.append(f'<rect class="hl" data-b="{bl.bar.number}" data-n="{nb}" data-bx="{",".join(f(v) for v in bxs)}" '
                        f'x="{f(bl.x + 0.1)}" y="-1.6" width="{f(bl.w - 0.2)}" height="7.2" rx="0.5"/>')
    cv.items.append(f'<line class="ph" x1="0" y1="-1.6" x2="0" y2="5.6" stroke-width="0.22"/>')
    for k in range(5):
        cv.line(GUTTER, k, x_end, k, STAFF_LINE, "staff")
    cv.merge(note_cv)
    top = min(note_cv.ymin, 0.0)

    outlines = []
    for bi, bl in enumerate(bars):
        bar = bl.bar
        px = bl.x
        if bl.show_clef:
            cv.glyph("unpitchedPercussionClef1", px + 1.0, 2.0)
            px += CLEF_W
        if bl.show_time:
            draw_time_sig(cv, bar.meter, px)
        xe = bl.x1
        if is_last_system and bi == len(bars) - 1:
            cv.rect(xe - THICK_BAR, 0, THICK_BAR, 4, "ink")
            cv.rect(xe - THICK_BAR - BAR_SEP - THIN_BAR, 0, THIN_BAR, 4, "ink")
        elif bl.last_in_section:
            cv.rect(xe - THIN_BAR, 0, THIN_BAR, 4, "ink")
            cv.rect(xe - THIN_BAR * 2 - BAR_SEP, 0, THIN_BAR, 4, "ink")
        else:
            cv.rect(xe - THIN_BAR / 2, 0, THIN_BAR, 4, "ink")
        bx0, bx1 = bl.body_x0, bl.x1
        cxm = (bx0 + bx1) / 2
        if bar.simile == 1:
            w = gw("repeat1Bar")
            cv.glyph("repeat1Bar", cxm - w / 2, 2.0)
        elif bar.simile == 3:
            w = gw("repeat2Bars")
            cv.glyph("repeat2Bars", bl.x - w / 2, 2.0)
        if bar.simile:
            strong = bl.sec_index % 4 == 0
            cv.text(cxm, -1.05, str(bl.sec_index), 1.3 if strong else 1.15,
                    "simile-num strong" if strong else "simile-num", "middle")
        if bar.rest_bars:
            mx0, mx1 = bx0 + 1.6, bx1 - 1.6
            cv.rect(mx0, 1.5, mx1 - mx0, 1.0, "ink")
            cv.rect(mx0, 1.0, THIN_BAR, 2.0, "ink")
            cv.rect(mx1 - THIN_BAR, 1.0, THIN_BAR, 2.0, "ink")
            ds = [f"timeSig{d}" for d in str(bar.rest_bars)]
            wsum = sum(GLYPHS[d]["adv"] for d in ds)
            xx = cxm - wsum / 2
            for d in ds:
                cv.glyph(d, xx, -1.7)
                xx += GLYPHS[d]["adv"]
            top = min(top, -2.8)
        if bar.confidence in ("low", "medium"):
            tip = f"{bar.confidence.title()} confidence: {bar.confidence_note or 'best estimate'}"
            outlines.append((bx0 + 0.2, bx1 - bx0 - 0.6, bar.confidence, tip))

    # confidence outlines go behind the notation and around all of it (never across a note)
    if outlines:
        oy0, oy1 = min(cv.ymin, -1.2) - 0.45, max(cv.ymax, 5.2) + 0.45
        for ox, ow, conf, tip in reversed(outlines):
            cv.items.insert(0, f'<rect x="{f(ox)}" y="{f(oy0)}" width="{f(ow)}" height="{f(oy1 - oy0)}" rx="0.6" '
                               f'class="conf-{conf}"><title>{esc(tip)}</title></rect>')
        cv.ymin, cv.ymax = min(cv.ymin, oy0), max(cv.ymax, oy1)

    # ---------------- lanes above the staff ----------------
    lane_y = min(top, -1.0) - 0.5
    ferm = []
    for bl in bars:
        for d in bl.bar.directives:
            if d.kind == "fermata":
                beat = int(d.opts.get("beat", d.args[0] if d.args and d.args[0].isdigit() else "1")) - 1
                beat = max(0, min(beat, len(bl.group_x) - 1))
                ferm.append(bl.group_x[beat] + bl.note_off[beat])
    if ferm:
        for x in ferm:
            w = gw("fermataAbove")
            cv.glyph("fermataAbove", x - w / 2, lane_y)
        lane_y -= 1.9
    dyn_items = [(bi, bl, d) for bi, bl in enumerate(bars) for d in bl.bar.directives if d.kind in ("dyn", "cresc", "dim")]
    if dyn_items or sl.carry:
        yd = lane_y - 0.75          # baseline; the f/p descenders stay clear of the stems below
        for kind, rem in sl.carry:          # continuation: starts half open, ends where the line ends or it does
            last = bars[min(len(bars), rem) - 1]
            hx0, hx1, hy, o = bars[0].body_x0 + 0.3, last.x1 - 0.9, yd - 0.45, 0.6
            a, b = (0.3, o) if kind == "cresc" else (0.3, 0.0)
            cv.line(hx0, hy - a, hx1, hy - b, HAIRPIN, "ink-stroke")
            cv.line(hx0, hy + a, hx1, hy + b, HAIRPIN, "ink-stroke")
        for bi, bl, d in dyn_items:
            if d.kind == "dyn" and d.args:
                beat = int(d.opts.get("beat", "1")) - 1
                beat = max(0, min(beat, len(bl.group_x) - 1))
                xx = bl.group_x[beat] + bl.note_off[beat] - 0.6
                for gname in dynamic_glyphs(d.args[0].lower()):
                    cv.glyph(gname, xx, yd)
                    xx += GLYPHS[gname]["adv"] + 0.05
            elif d.kind in ("cresc", "dim"):
                nb = int(d.opts.get("bars", d.args[0] if d.args and d.args[0].isdigit() else "1"))
                last = bars[min(len(bars) - 1, bi + nb - 1)]
                has_dyn = any(dd.kind == "dyn" for dd in bl.bar.directives)
                hx0 = bl.body_x0 + 0.8 + (3.2 if has_dyn else 0)
                hx1 = last.x1 - 0.9
                hy = yd - 0.45
                o = 0.6
                if d.kind == "cresc":
                    cv.line(hx0, hy, hx1, hy - o, HAIRPIN, "ink-stroke")
                    cv.line(hx0, hy, hx1, hy + o, HAIRPIN, "ink-stroke")
                else:
                    cv.line(hx0, hy - o, hx1, hy, HAIRPIN, "ink-stroke")
                    cv.line(hx0, hy + o, hx1, hy, HAIRPIN, "ink-stroke")
        lane_y = yd - 2.5          # f is 1.8 sp tall: room above it before the cue text
    texts = []
    for bi, bl in enumerate(bars):
        bar = bl.bar
        x = bl.body_x0 + 0.3
        for d in bar.directives:
            if d.kind in ("text", "cue", "stop", "feel", "fill"):
                t = " ".join(d.args) if d.args else {"stop": "Stop", "fill": "Fill"}.get(d.kind, "")
                if t:
                    texts.append((x, t))
            elif d.kind in ("rit", "accel", "atempo"):
                lab = {"rit": "rit.", "accel": "accel.", "atempo": "a tempo"}[d.kind]
                texts.append((x, lab + ((" " + " ".join(d.args)) if d.args else "")))
        if bar.rest_text:
            texts.append((x, bar.rest_text))
    if texts:
        size = 1.5
        rows: List[float] = []
        yt0 = lane_y - 0.15
        placed = []
        for x, t in texts:
            w = text_w(t, size, 0.47)
            r = 0
            while r < len(rows) and rows[r] > x - 0.5:
                r += 1
            if r == len(rows):
                rows.append(-1e9)
            rows[r] = x + w
            placed.append((x, yt0 - r * 1.9, t))
        for x, y, t in placed:
            cv.text(x, y, t, size, "cue")
        lane_y = yt0 - len(rows) * 1.9
    tempo_marks = [(bl.body_x0 + 0.2, " ".join(d.args)) for bi, bl in enumerate(bars) if bi > 0
                   for d in bl.bar.directives if d.kind == "tempo" and d.args]
    if tempo_marks:
        y = lane_y - 0.3
        for x, spec in tempo_marks:
            bpm, unit, label = tempo_parts(spec)
            gname = {"q": "metNoteQuarterUp", "h": "metNoteHalfUp", "e": "metNote8thUp"}[unit[0]]
            xx = x
            if label:
                cv.text(xx, y, label, 1.45, "tempo")
                xx += text_w(label, 1.45, 0.55) + 0.6
            cv.glyph(gname, xx, y, 0.9)
            xx += gw(gname) * 0.9 + 0.2
            if unit.endswith("."):
                cv.glyph("metAugmentationDot", xx, y, 0.9)
                xx += 0.6
            cv.text(xx + 0.15, y, f"= {bpm}", 1.45, "tempo")

    first = bars[0].bar
    cv.text(GUTTER + 0.15, -1.25, str(first.number), 1.1, "barnum")

    y0 = min(cv.ymin, -1.5) - 0.6
    y1 = cv.ymax + 0.6
    last_bar = bars[-1].bar
    lastnum = last_bar.number + (last_bar.rest_bars - 1 if last_bar.rest_bars else 0)
    staff_svg = (f'<svg class="staff-svg" viewBox="0 {f(y0)} {f(x_end + 0.6)} {f(y1 - y0)}" '
                 f'style="--w:{f(x_end + 0.6)}" role="img" aria-label="Bars {_fmt_range(first.number, lastnum)}">'
                 + "".join(cv.items) + "</svg>")

    # ---------------- header lane (HTML): section box + tempo ----------------
    head_bits = []
    if sl.section_start and sec is not None:
        nb = sum((b.rest_bars or 1) for b in sec.bars)
        mark = f'<span class="mark">{esc(sec.mark)}</span>' if sec.mark else ""
        meta = f"{nb} bar{'s' if nb != 1 else ''}" + (f" · {esc(sec.at)}" if sec.at else "")
        conf = (f'<span class="conf-chip conf-{sec.confidence}" title="{esc(sec.confidence_note)}">'
                f'{esc(sec.confidence)} confidence</span>' if sec.confidence in ("medium", "low") else "")
        head_bits.append(f'{mark}<span class="secbox">{esc(sec.name)}</span><span class="secmeta">{meta}</span>{conf}')
    tdir = [d for d in first.directives if d.kind == "tempo" and d.args]
    if tdir:
        bpm, unit, label = tempo_parts(" ".join(tdir[0].args))
        head_bits.append(tempo_html(bpm, unit, label))
    elif first_system:
        bpm, unit, label = tempo_parts(chart.meta.get("tempo", ""))
        feel = chart.meta.get("style") or chart.meta.get("feel") or ""
        if bpm:
            head_bits.append(tempo_html(bpm, unit, feel))
    head_html = f'<div class="sys-head">{"".join(head_bits)}</div>' if head_bits else ""

    # ---------------- counts (+ sticking row) ----------------
    cc = Canvas()
    has_st = any(bl.vb.sticking for bl in bars if not bl.bar.simile)
    H = COUNT_H + (STICK_H if has_st else 0)
    cc.ymin, cc.ymax = 0, H
    mode = chart.meta.get("counting", "").lower()
    for bl in bars:
        bar = bl.bar
        if bar.rest_bars:
            cc.text((bl.body_x0 + bl.x1) / 2, 1.55, f"bars {bar.number}–{bar.number + bar.rest_bars - 1}", 1.15,
                    "count-sub", "middle")
            cc.rect(bl.x1 - 0.05, 0.1, 0.1, COUNT_H - 0.2, "grid-bar")
            continue
        sizes = bar.group_sizes()
        onsets = {(h.group, h.slot) for h in bar.hits if h.inst != STICKING_ROW}
        items = []
        for g in range(len(bar.meter.groups)):
            n = sizes[g]
            labs = count_labels(bar.meter, g, n, mode)
            if g % 2 == 1:
                cc.rect(bl.group_x[g], 0.15, bl.group_w[g], COUNT_H - 0.3, "beat-band")
            slot = bl.group_w[g] / n
            small = slot < 1.75
            for k, (lab, main) in enumerate(labs):
                if not main and (slot < (1.5 if bar.simile else 0.9) or (slot < 1.3 and (g, k) not in onsets)):
                    continue        # too narrow: keep beat numbers and the counts of played notes
                if small and lab in ("trip", "let"):
                    lab = {"trip": "tr", "let": "l"}[lab]
                cls = "count-main" if main else ("count-on" if (g, k) in onsets else "count-sub")
                items.append(f'<text x="{f(bl.slot_x(g, k, n))}" y="1.6" font-size="{f(1.3 if main else 1.05)}" '
                             f'text-anchor="middle" class="{cls}">{esc(lab)}</text>')
        cc.items.append(f'<g{" class=sim" if bar.simile else ""}>' + "".join(items) + "</g>")
        if has_st and not bar.simile:
            for (g, k), ch in bl.vb.sticking.items():
                cc.text(bl.slot_x(g, k, sizes[g]), COUNT_H + 1.35, ch, 1.25, "sticking", "middle")
        cc.rect(bl.x1 - 0.05, 0.1, 0.1, COUNT_H - 0.2, "grid-bar")
    counts_svg = (f'<svg class="counts-svg" viewBox="0 0 {f(x_end + 0.6)} {f(H)}" style="--w:{f(x_end + 0.6)}" aria-hidden="true">'
                  + "".join(cc.items) + "</svg>")

    # ---------------- colour grid ----------------
    used = {h.inst for bl in bars for h in bl.bar.hits if h.inst != STICKING_ROW}
    rows = sorted(used, key=lambda c: INSTRUMENTS[c].order)
    gc = Canvas()
    GH = max(1, len(rows)) * GRID_ROW + 0.4
    gc.ymin, gc.ymax = 0, GH
    for r, inst in enumerate(rows):
        yc = 0.2 + r * GRID_ROW + GRID_ROW / 2
        gc.text(GUTTER - 0.5, yc + 0.42, INSTRUMENTS[inst].short, 1.15, "grid-label", "end")
        gc.line(GUTTER, yc + GRID_ROW / 2, x_end, yc + GRID_ROW / 2, 0.05, "grid-line")
    if rows:
        gc.line(GUTTER, 0.2, x_end, 0.2, 0.05, "grid-line")
    for bl in bars:
        bar = bl.bar
        for g in range(len(bar.meter.groups)):
            if g % 2 == 1 and not bar.rest_bars:
                gc.rect(bl.group_x[g], 0.2, bl.group_w[g], GH - 0.4, "beat-band")
        gc.rect(bl.x1 - 0.05, 0.2, 0.1, GH - 0.4, "grid-bar")
        if bar.rest_bars:
            continue
        marks = []
        for h in bar.hits:
            if h.inst == STICKING_ROW or h.inst not in rows:
                continue
            yc = 0.2 + rows.index(h.inst) * GRID_ROW + GRID_ROW / 2
            xc = bl.slot_x(h.group, h.slot, h.nslots)
            mk = _grid_mark(xc, yc, h, FAMILY_CLASS[INSTRUMENTS[h.inst].family], bl)
            k = min(1.0, (bl.group_w[h.group] / h.nslots) / 1.55)   # narrow slots: smaller marks, no overlap
            if k < 0.98:
                mk = f'<g transform="translate({f(xc)} {f(yc)}) scale({k:.3f}) translate({f(-xc)} {f(-yc)})">{mk}</g>'
            marks.append(mk)
        if marks:
            gc.items.append(f'<g{" class=sim" if bar.simile else ""}>' + "".join(marks) + "</g>")
    grid_svg = (f'<svg class="grid-svg" viewBox="0 0 {f(x_end + 0.6)} {f(GH)}" style="--w:{f(x_end + 0.6)}" aria-hidden="true">'
                + "".join(gc.items) + "</svg>")

    return RenderedSystem(head_html, staff_svg, counts_svg, grid_svg, x_end + 0.6,
                          section_id(sec) if sec else "", first.number, lastnum)


def _grid_mark(x: float, y: float, h, fam: str, bl: BarLayout) -> str:
    a = h.art
    s = 1.12
    c = f"m-{fam}"
    if a == "g":
        s2 = 0.84
        return (f'<rect x="{f(x - s2 / 2)}" y="{f(y - s2 / 2)}" width="{f(s2)}" height="{f(s2)}" rx="0.22" '
                f'class="{c} ghost-mark"/>')
    if a in "oO" and h.inst in ("HH", "HF"):
        r = 0.5 if a == "o" else 0.62
        return f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" class="{c} open-mark"/>'
    if a == "h":
        return (f'<circle cx="{f(x)}" cy="{f(y)}" r="0.5" class="{c} open-mark"/>'
                f'<path d="M{f(x - 0.5)} {f(y)} A0.5 0.5 0 0 0 {f(x + 0.5)} {f(y)} Z" class="{c}"/>')
    if a in "bB":
        r = 0.68 if a == "b" else 0.82
        return f'<polygon points="{f(x)},{f(y - r)} {f(x + r)},{f(y)} {f(x)},{f(y + r)} {f(x - r)},{f(y)}" class="{c}"/>'
    if a == "c":
        d = 0.48
        return (f'<path d="M{f(x - d)} {f(y - d)} L{f(x + d)} {f(y + d)} M{f(x + d)} {f(y - d)} L{f(x - d)} {f(y + d)}" '
                f'class="{c}-stroke" stroke-width="0.3" stroke-linecap="round"/>')
    if a == "z":
        n, g = h.nslots, h.group
        x2 = bl.slot_x(g, h.slot + 1, n) if h.slot + 1 < n else bl.group_x[g] + bl.group_w[g]
        w = max(s, x2 - x + s / 2 - 0.15)
        return f'<rect x="{f(x - s / 2)}" y="{f(y - 0.32)}" width="{f(w)}" height="0.64" rx="0.32" class="{c}"/>'
    out = ""
    if a in "fF":
        out += f'<rect x="{f(x - s / 2 - 0.72)}" y="{f(y - 0.3)}" width="0.6" height="0.6" rx="0.18" class="{c}"/>'
    if a == "d":
        out += (f'<circle cx="{f(x - s / 2 - 0.9)}" cy="{f(y)}" r="0.22" class="{c}"/>'
                f'<circle cx="{f(x - s / 2 - 0.38)}" cy="{f(y)}" r="0.22" class="{c}"/>')
    if a in "XOFBR":
        s = 1.4
        out += f'<rect x="{f(x - s / 2)}" y="{f(y - s / 2)}" width="{f(s)}" height="{f(s)}" rx="0.3" class="{c} accent-mark"/>'
    else:
        out += f'<rect x="{f(x - s / 2)}" y="{f(y - s / 2)}" width="{f(s)}" height="{f(s)}" rx="0.28" class="{c}"/>'
    if a in "rR":
        out += f'<line x1="{f(x - 0.45)}" y1="{f(y + 0.45)}" x2="{f(x + 0.45)}" y2="{f(y - 0.45)}" stroke-width="0.2" class="cut"/>'
    if a == "k":
        out += f'<line x1="{f(x + 0.8)}" y1="{f(y - 0.6)}" x2="{f(x + 0.8)}" y2="{f(y + 0.6)}" stroke-width="0.2" class="ink-stroke"/>'
    return out
