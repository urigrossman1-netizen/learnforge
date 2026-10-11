"""Turn a Bar's grid into engraving-ready voice elements.

Conventions (pro drum transcription style):
  * two voices: hands (stems up) and feet (stems down)
  * a note lasts until the next onset in its voice, never past the beat
  * rests fill the beat where a voice is silent; silent half-bars merge to
    half rests; a voice that is silent for the whole bar is omitted
  * beams group by beat; partial beams (stubs) for dotted rhythms
  * tuplets get a number (bracket only when not fully beamed)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction as Fr
from math import gcd
from typing import Dict, List, Optional, Tuple

from .model import INSTRUMENTS, STICKING_ROW, Bar

# notehead / articulation overrides by (instrument, articulation char)
HEAD_OVERRIDES = {
    ("SN", "c"): "noteheadXBlack",          # cross-stick / side-stick: x on the snare space (Weinberg)
    ("SN", "r"): "noteheadSlashedBlack2",   # rimshot: slashed head (not circled: too close to a ghost)
    ("SN", "R"): "noteheadSlashedBlack2",   # accented rimshot
    ("RD", "b"): "noteheadDiamondBlack",    # ride bell
    ("RD", "B"): "noteheadDiamondBlack",
    ("R2", "b"): "noteheadDiamondBlack",
    ("R2", "B"): "noteheadDiamondBlack",
}

ACCENT_CHARS = set("XOFBR")
GHOST_CHARS = set("g")
FLAM_CHARS = set("fF")
DRAG_CHARS = set("d")
BUZZ_CHARS = set("z")
OPEN_CHARS = set("oO")
HALF_CHARS = set("h")
CHOKE_CHARS = set("k")


def _is_pow2(f: Fr) -> bool:
    if f <= 0:
        return False
    n, d = f.numerator, f.denominator
    return (n & (n - 1) == 0) and (d & (d - 1) == 0)


def representable(total: Fr) -> Optional[Tuple[Fr, int]]:
    """Return (base value, dots) if total is a plain or single-dotted note value."""
    if _is_pow2(total):
        return total, 0
    base = total * Fr(2, 3)
    if _is_pow2(base):
        return base, 1
    return None


def decompose(total: Fr) -> List[Tuple[Fr, int]]:
    """Split a duration into representable values, largest first."""
    out = []
    rem = total
    guard = 0
    while rem > 0 and guard < 16:
        guard += 1
        r = representable(rem)
        if r:
            out.append(r)
            break
        # largest power of two <= rem
        v = Fr(1, 1)
        while v > rem:
            v /= 2
        # prefer dotted if it fits
        if v * Fr(3, 2) <= rem:
            out.append((v, 1))
            rem -= v * Fr(3, 2)
        else:
            out.append((v, 0))
            rem -= v
    return out


@dataclass
class NoteHead:
    inst: str
    art: str
    pos: int
    head: str
    accent: bool = False
    ghost: bool = False
    flam: bool = False
    drag: bool = False
    buzz: bool = False
    open: bool = False
    half: bool = False
    closed: bool = False     # '+' mark (set later)
    choke: bool = False
    shift: int = 0           # +1 = displaced right of the stem (seconds in up-stem chords), -1 left


@dataclass
class Elem:
    kind: str                # "chord" | "rest" | "mrest" (whole-bar rest) | "simile"
    voice: str               # "up" | "down"
    group: int
    slot: int                # slot index within group where the element starts
    nslots: int              # slots in the group
    onset: Fr
    value: Fr                # written base value (1/4, 1/8, ...)
    dots: int = 0
    notes: List[NoteHead] = field(default_factory=list)
    tuplet: Optional[Tuple[int, int]] = None
    beam: Optional[int] = None      # beam id (index into VoiceBar.beams)
    span_slots: int = 1             # how many slots of the group this element covers
    merged: bool = False            # rest shared by both voices -> drawn once, centred
    hidden: bool = False            # the other half of a merged rest pair

    @property
    def flags(self) -> int:
        """number of beams/flags for this value (8th=1, 16th=2, 32nd=3)."""
        v = self.value
        n = 0
        while v < Fr(1, 4):
            v *= 2
            n += 1
        return n


@dataclass
class Beam:
    voice: str
    group: int
    elems: List[int]         # indices into VoiceBar.elems (chords and inner rests)
    tuplet: Optional[Tuple[int, int]] = None


@dataclass
class TupletMark:
    voice: str
    group: int
    number: int
    first: int               # elem index
    last: int
    bracket: bool
    partial: bool = False    # covers only part of its beat (always bracketed)


@dataclass
class VoiceBar:
    elems: List[Elem] = field(default_factory=list)
    beams: List[Beam] = field(default_factory=list)
    tuplets: List[TupletMark] = field(default_factory=list)
    sticking: Dict[Tuple[int, int], str] = field(default_factory=dict)  # (group, slot) -> R/L


def group_slot_value(D: Fr, n: int) -> Tuple[Fr, Optional[Tuple[int, int]]]:
    """Written value of one slot and the tuplet ratio (n, m) if any."""
    actual = D / n
    if representable(actual):
        return actual, None
    sv = Fr(1, 1)
    while sv / 2 >= actual:
        sv /= 2
    # smallest power of two >= actual
    while sv < actual:
        sv *= 2
    m = D / sv
    if m.denominator != 1:
        # fall back: treat as plain
        return actual, None
    return sv, (n, int(m))


def build_notehead(inst: str, art: str) -> NoteHead:
    I = INSTRUMENTS[inst]
    head = HEAD_OVERRIDES.get((inst, art), I.head)
    return NoteHead(
        inst=inst, art=art, pos=I.pos, head=head,
        accent=art in ACCENT_CHARS, ghost=art in GHOST_CHARS, flam=art in FLAM_CHARS,
        drag=art in DRAG_CHARS, buzz=art in BUZZ_CHARS,
        open=(art in OPEN_CHARS), half=art in HALF_CHARS, choke=art in CHOKE_CHARS,
    )


def _span_nr(slots: List[int], a: int, b: int) -> int:
    """Subdivision needed for the onsets in slots [a, b) (0 = no onsets)."""
    ks = [k - a for k in slots if a <= k < b]
    if not ks:
        return 0
    d = b - a
    for k in ks:
        d = gcd(d, k)
    return (b - a) // d


def _span_elems(voice: str, hits, g: int, n: int, a: int, b: int, onset0: Fr, D: Fr,
                slots: List[int]) -> List["Elem"]:
    """Notes and rests for slots [a, b) of group g (n slots, duration D)."""
    m = b - a
    Ds = D * Fr(m, n)
    start = onset0 + D * Fr(a, n)
    ks = [k - a for k in slots if a <= k < b]
    if not ks:
        val, dots = representable(Ds) or (Ds, 0)
        return [Elem("rest", voice, g, a, n, start, val, dots, span_slots=m)]
    d = m
    for k in ks:
        d = gcd(d, k)
    nr = m // d
    sv, tup = group_slot_value(Ds, nr)
    rs = [k // d for k in ks]
    els: List[Elem] = []
    if rs[0] > 0:
        pos = 0
        for val, dots in decompose(rs[0] * sv):
            span = int((val * (Fr(3, 2) if dots else 1)) / sv)
            els.append(Elem("rest", voice, g, a + pos * d, n, start + Ds * Fr(pos, nr), val, dots,
                            tuplet=tup, span_slots=span * d))
            pos += span
    for i, k in enumerate(rs):
        k2 = rs[i + 1] if i + 1 < len(rs) else nr
        parts = decompose((k2 - k) * sv)
        val, dots = parts[0]
        notes = sorted(hits[(g, a + k * d)], key=lambda x: x.pos)
        span = int((val * (Fr(3, 2) if dots else 1)) / sv)
        els.append(Elem("chord", voice, g, a + k * d, n, start + Ds * Fr(k, nr), val, dots, notes,
                        tuplet=tup, span_slots=span * d))
        pos = k + span
        for val2, dots2 in parts[1:]:
            span2 = int((val2 * (Fr(3, 2) if dots2 else 1)) / sv)
            els.append(Elem("rest", voice, g, a + pos * d, n, start + Ds * Fr(pos, nr), val2, dots2,
                            tuplet=tup, span_slots=span2 * d))
            pos += span2
    return els


def engrave_bar(bar: Bar, hh_state: Dict[str, bool]) -> VoiceBar:
    """Build voice elements for a bar.  hh_state carries 'was the last hi-hat open?'
    across bars so a closing '+' can be shown on the first closed hit after an open one."""
    vb = VoiceBar()
    meter = bar.meter
    sizes = bar.group_sizes()

    # sticking
    if STICKING_ROW in bar.rows:
        for g, s in enumerate(bar.rows[STICKING_ROW]):
            for k, ch in enumerate(s):
                if ch in "RLB":
                    vb.sticking[(g, k)] = ch

    # gather hits by voice / group / slot
    by_voice: Dict[str, Dict[Tuple[int, int], List[NoteHead]]] = {"up": {}, "down": {}}
    for h in sorted(bar.hits, key=lambda h: (h.onset, INSTRUMENTS[h.inst].order if h.inst in INSTRUMENTS else 99)):
        if h.inst == STICKING_ROW:
            continue
        I = INSTRUMENTS[h.inst]
        nh = build_notehead(h.inst, h.art)
        by_voice[I.voice].setdefault((h.group, h.slot), []).append(nh)

    # hi-hat open/closed marks in time order
    for key in sorted(by_voice["up"].keys()):
        for nh in by_voice["up"][key]:
            if nh.inst == "HH":
                if nh.open or nh.half:
                    hh_state["open"] = True
                else:
                    if hh_state.get("open"):
                        nh.closed = True
                    hh_state["open"] = False
    voices_present = [v for v in ("up", "down") if by_voice[v]]
    if not voices_present:
        vb.elems.append(Elem("mrest", "up", 0, 0, sizes[0], Fr(0), meter.length))
        return vb

    for voice in ("up", "down"):
        hits = by_voice[voice]
        if not hits:
            continue  # silent voice for the whole bar: omitted
        group_elems: List[List[Elem]] = []
        onset0 = Fr(0)
        for g, D in enumerate(meter.groups):
            n = sizes[g]
            slots = sorted(k for (gg, k) in hits if gg == g)
            if not slots:
                group_elems.append([])  # filled with a beat rest below
                onset0 += D
                continue
            # engrave with the coarsest subdivision that still holds every onset of this voice
            # (e.g. a triplet beat with only its downbeat played is a plain quarter note)
            d = n
            for k in slots:
                d = gcd(d, k)
            spans = [(0, n)]
            if n // d == 6 and not meter.compound:
                # 8th + 16th-note triplet (or the reverse) reads far better than a sextuplet:
                # split the beat in halves when one half holds at most its downbeat
                h = n // 2
                if min(_span_nr(slots, 0, h), _span_nr(slots, h, n)) <= 1:
                    spans = [(0, h), (h, n)]
            els: List[Elem] = []
            for a, b in spans:
                els.extend(_span_elems(voice, hits, g, n, a, b, onset0, D, slots))
            group_elems.append(els)
            onset0 += D

        # beat rests for silent groups, merging half-bar pairs in 4-group meters
        ng = len(meter.groups)
        equal = len(set(meter.groups)) == 1
        g = 0
        onset = Fr(0)
        filled: List[List[Elem]] = []
        while g < ng:
            D = meter.groups[g]
            if group_elems[g]:
                filled.append(group_elems[g])
            elif equal and ng == 4 and g % 2 == 0 and not group_elems[g + 1]:
                val, dots = representable(D * 2) or (D * 2, 0)
                filled.append([Elem("rest", voice, g, 0, sizes[g], onset, val, dots, span_slots=sizes[g])])
                filled.append([])
                onset += D
                g += 1
            else:
                val, dots = representable(D) or (D, 0)
                filled.append([Elem("rest", voice, g, 0, sizes[g], onset, val, dots, span_slots=sizes[g])])
            onset += D
            g += 1

        # flatten + beams + tuplets
        for g, els in enumerate(filled):
            base = len(vb.elems)
            vb.elems.extend(els)
            if not els:
                continue
            idx = list(range(base, base + len(els)))
            # contiguous runs of beamable chords (rests allowed inside, quarter+ chords break)
            runs: List[List[int]] = []
            cur: List[int] = []
            for i in idx:
                e = vb.elems[i]
                if e.kind == "chord" and e.value < Fr(1, 4):
                    cur.append(i)
                elif e.kind == "chord":
                    if cur:
                        runs.append(cur)
                    cur = []
                else:  # rest
                    if cur:
                        cur.append(i)
            if cur:
                runs.append(cur)
            for r in runs:
                while r and vb.elems[r[-1]].kind == "rest":
                    r.pop()
                if sum(1 for i in r if vb.elems[i].kind == "chord") >= 2:
                    bid = len(vb.beams)
                    vb.beams.append(Beam(voice, g, r, els[0].tuplet))
                    for i in r:
                        vb.elems[i].beam = bid
            # tuplet marks: one per run of elements sharing a tuplet ratio
            truns: List[List] = []
            for i in idx:
                t = vb.elems[i].tuplet
                if t and truns and truns[-1][0] == t and truns[-1][2] == i - 1:
                    truns[-1][2] = i
                elif t:
                    truns.append([t, i, i])
            for tup, i0, i1 in truns:
                if i0 == idx[0] and i1 == idx[-1]:
                    chords = [i for i in idx if vb.elems[i].kind == "chord"]
                    fully = (len(chords) >= 2 and all(vb.elems[i].beam is not None for i in chords)
                             and len({vb.elems[i].beam for i in chords}) == 1
                             and vb.elems[idx[0]].kind == "chord" and vb.elems[idx[-1]].kind == "chord")
                    vb.tuplets.append(TupletMark(voice, g, tup[0], i0, i1, bracket=not fully))
                else:   # part of a beat (8th + 16th triplet): bracket the tuplet notes only
                    vb.tuplets.append(TupletMark(voice, g, tup[0], i0, i1, bracket=True, partial=True))

    # both voices resting for the same span -> one centred rest (less clutter)
    ups = {(e.onset, e.value, e.dots): i for i, e in enumerate(vb.elems)
           if e.kind == "rest" and e.voice == "up" and e.beam is None}
    for e in vb.elems:
        if e.kind == "rest" and e.voice == "down" and e.beam is None:
            k = (e.onset, e.value, e.dots)
            if k in ups:
                vb.elems[ups[k]].merged = True
                e.hidden = True

    # displace seconds within up-stem chords (upper note of a second goes right)
    for e in vb.elems:
        if e.kind != "chord" or len(e.notes) < 2:
            continue
        ns = sorted(e.notes, key=lambda x: x.pos)
        if e.voice == "up":
            prev = None
            for nh in ns:
                if prev is not None and nh.pos - prev.pos == 1 and prev.shift == 0:
                    nh.shift = 1
                prev = nh
        else:
            prev = None
            for nh in reversed(ns):
                if prev is not None and prev.pos - nh.pos == 1 and prev.shift == 0:
                    nh.shift = -1
                prev = nh
        # unison (same position, different instruments) -> shift the later one
        seen = {}
        for nh in ns:
            if nh.pos in seen:
                nh.shift = 1 if e.voice == "up" else -1
            seen[nh.pos] = nh
    return vb
