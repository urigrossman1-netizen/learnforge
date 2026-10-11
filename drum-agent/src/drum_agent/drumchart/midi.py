"""General MIDI drum track (channel 10) of a .drums chart, as written.

Tempo changes, time signatures, multi-bar rests, accents, ghost notes, flams,
drags and buzz rolls all come from the parsed chart, so the MIDI is exactly
what the page shows and plays. Standard library only (writes the file itself).
"""

from __future__ import annotations

import struct
from fractions import Fraction as Fr
from pathlib import Path

from .model import Chart

TPB = 480  # ticks per quarter note

# (instrument, articulation) -> GM percussion note; articulation None = any
GM = {
    ("BD", None): 36, ("B2", None): 35,
    ("SN", "c"): 37, ("SN", None): 38,
    ("HH", "o"): 46, ("HH", "O"): 46, ("HH", "h"): 46, ("HH", None): 42,
    ("HF", "o"): 46, ("HF", None): 44,
    ("RD", "b"): 53, ("RD", "B"): 53, ("RD", None): 51,
    ("R2", "b"): 53, ("R2", "B"): 53, ("R2", None): 59,
    ("CR", None): 49, ("C2", None): 57, ("CH", None): 52, ("SP", None): 55,
    ("CB", None): 56, ("TB", None): 54,
    ("T1", None): 50, ("T2", None): 48, ("T3", None): 47, ("FT", None): 43, ("F2", None): 41,
}
ACCENTED = set("XOFBR")


def gm_note(inst: str, art: str) -> int | None:
    return GM.get((inst, art), GM.get((inst, None)))


def velocity(art: str) -> int:
    if art == "g":
        return 38
    if art == "h":
        return 80
    return 118 if art in ACCENTED else 92


def _vlq(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def chart_events(chart: Chart) -> list[tuple[int, int, bytes]]:
    """(tick, order, raw MIDI event) for the whole chart; order puts meta before offs before ons."""
    events: list[tuple[int, int, bytes]] = []
    tick = Fr(0)
    tempo, meter = None, None
    for bar in chart.bars:
        t0 = round(tick)
        if bar.tempo != tempo:
            micro = round(60_000_000 / float(bar.tempo))
            events.append((t0, 0, b"\xff\x51\x03" + micro.to_bytes(3, "big")))
            tempo = bar.tempo
        if (bar.meter.num, bar.meter.den) != meter:
            den_pow = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4}[bar.meter.den]
            events.append((t0, 0, bytes([0xFF, 0x58, 0x04, bar.meter.num, den_pow, 24, 8])))
            meter = (bar.meter.num, bar.meter.den)
        whole = 4 * TPB  # ticks per whole note
        if not bar.rest_bars:
            for h in bar.hits:
                note = gm_note(h.inst, h.art)
                if note is None:
                    continue
                at = tick + h.onset * whole
                slot = bar.meter.groups[h.group] / h.nslots * whole
                strokes = [(at, velocity(h.art))]
                if h.art in "fF":
                    strokes.insert(0, (at - Fr(TPB, 16), 50))
                elif h.art == "d":
                    strokes[:0] = [(at - Fr(TPB, 8), 45), (at - Fr(TPB, 16), 45)]
                elif h.art == "z":
                    strokes = [(at + slot * k / 6, 60) for k in range(6)]
                for when, vel in strokes:
                    on = max(0, round(when))
                    length = max(10, round(min(slot, Fr(TPB, 2)) * Fr(9, 10)))
                    events.append((on, 2, bytes([0x99, note, vel])))
                    events.append((on + length, 1, bytes([0x89, note, 0])))
        tick += bar.meter.length * whole * (bar.rest_bars or 1)
    return events


def write_midi(chart: Chart, path: str | Path) -> Path:
    events = chart_events(chart)
    track = bytearray(b"\x00\xff\x03\x05Drums")
    now = 0
    for t, _, ev in sorted(events, key=lambda e: (e[0], e[1])):
        track += _vlq(t - now) + ev
        now = t
    track += b"\x00\xff\x2f\x00"
    data = b"MThd" + struct.pack(">IHHH", 6, 0, 1, TPB) + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
