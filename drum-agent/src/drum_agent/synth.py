"""A synthetic song with known drum ground truth, for tests and `doctor`.

Drums, a bass line and a chord pad over a verse/chorus/verse form with
fills and crashes, slightly humanized, so the transcriber is checked against
something closer to a mix than an isolated drum loop.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt

SR = 44100

# 16-step patterns (16th notes in 4/4).
_EIGHTHS = [0, 2, 4, 6, 8, 10, 12, 14]
GROOVE_VERSE = {"kick": [0, 7, 8], "snare": [4, 12], "hihat": _EIGHTHS}
GROOVE_CHORUS = {"kick": [0, 3, 8, 10], "snare": [4, 12], "hihat": list(range(16))}
FILL = {"kick": [0, 8], "snare": [4, 10, 11, 12, 13, 14, 15], "hihat": [0, 2, 4, 6, 8]}

# (bars, groove) per section; the last bar of the first two sections is a fill.
FORM = [("verse", 8, GROOVE_VERSE), ("chorus", 8, GROOVE_CHORUS), ("verse", 4, GROOVE_VERSE)]


def _hp(x, f):
    return sosfilt(butter(4, f, "highpass", fs=SR, output="sos"), x)


def _bp(x, lo, hi):
    return sosfilt(butter(2, [lo, hi], "bandpass", fs=SR, output="sos"), x)


def _sounds(rng):
    t = lambda d: np.arange(int(d * SR)) / SR  # noqa: E731
    tk = t(0.35)
    freq = 45 + 110 * np.exp(-tk / 0.03)
    kick = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-tk / 0.12)
    kick[:200] += rng.normal(0, 0.3, 200) * np.exp(-np.arange(200) / 40)
    ts = t(0.3)
    snare = 0.5 * np.sin(2 * np.pi * 185 * ts) * np.exp(-ts / 0.05)
    snare += 0.8 * _bp(rng.normal(0, 1, ts.size), 1000, 9000) * np.exp(-ts / 0.1)
    th = t(0.12)
    hihat = 0.35 * _hp(rng.normal(0, 1, th.size), 7000) * np.exp(-th / 0.025)
    tc = t(2.0)
    crash = 0.45 * _hp(rng.normal(0, 1, tc.size), 3500) * np.exp(-tc / 0.8)
    return {"kick": kick, "snare": snare, "hihat": hihat, "crash": crash}


def make_song(
    bpm: float = 96.0, lead_in: float = 0.5, seed: int = 7, backing: bool = True, gap: float = 0.0
):
    """Return (audio, sr, truth). truth['hits'] is a list of (time_s, drum).

    `gap` inserts that many seconds of silence (a stop) before the chorus.
    """
    rng = np.random.default_rng(seed)
    sounds = _sounds(rng)
    step = 60.0 / bpm / 4
    bars = sum(n for _, n, _ in FORM)
    total = lead_in + bars * 16 * step + gap + 2.5
    y = np.zeros(int(total * SR))
    hits: list[tuple[float, str]] = []
    sections = []

    def place(name, t0, vel):
        s = sounds[name]
        i = int(round(t0 * SR))
        y[i : i + s.size] += vel * s[: max(0, y.size - i)]

    bar = 0
    bar_starts = []
    for si, (sec_name, n_bars, groove) in enumerate(FORM):
        sections.append({"name": sec_name, "first_bar": bar + 1, "bars": n_bars})
        for b in range(n_bars):
            is_fill = b == n_bars - 1 and si < len(FORM) - 1
            pattern = FILL if is_fill else groove
            bar_start = lead_in + bar * 16 * step + (gap if si >= 1 else 0.0)
            bar_starts.append(bar_start)
            if b == 0 and bar > 0:
                hits.append((bar_start, "crash"))
                place("crash", bar_start, 0.9)
            for drum, steps in pattern.items():
                for s in steps:
                    t0 = bar_start + s * step + rng.normal(0, 0.004)
                    if drum == "hihat":
                        vel = 0.9 if s % 4 == 0 else 0.65
                    else:
                        vel = rng.uniform(0.8, 1.0)
                    hits.append((bar_start + s * step, drum))
                    place(drum, t0, vel)
            bar += 1

    if backing:
        y += 0.25 * _backing(bar_starts, step, y.size)
    y = 0.9 * y / np.max(np.abs(y))
    truth = {
        "bpm": bpm,
        "beats_per_bar": 4,
        "first_downbeat_s": lead_in,
        "bars": bars,
        "hits": sorted(hits),
        "sections": sections,
    }
    return y.astype(np.float32), SR, truth


def _backing(bar_starts, step, n):
    """Sawtooth bass on eighths plus a sine pad, one chord per bar."""
    roots = [55.0, 43.65, 65.41, 49.0]  # A1, F1, C2, G1
    out = np.zeros(n)
    for bar, t_bar in enumerate(bar_starts):
        root = roots[bar % 4]
        for e in range(8):
            t0 = t_bar + e * 2 * step
            dur = 2 * step * 0.9
            tt = np.arange(int(dur * SR)) / SR
            saw = 2 * ((tt * root) % 1) - 1
            env = np.minimum(1, tt / 0.015) * np.exp(-tt / 0.4)
            i = int(t0 * SR)
            seg = saw * env
            out[i : i + seg.size] += 0.6 * seg[: max(0, n - i)]
        dur = 16 * step
        tt = np.arange(int(dur * SR)) / SR
        pad = sum(np.sin(2 * np.pi * root * 4 * r * tt) for r in (1, 1.26, 1.5))
        pad *= np.minimum(1, tt / 0.2) * np.minimum(1, (dur - tt) / 0.2)
        i = int(t_bar * SR)
        out[i : i + pad.size] += 0.15 * pad[: max(0, n - i)]
    return sosfilt(butter(2, 2500, "lowpass", fs=SR, output="sos"), out)


def score(truth_hits, detected_hits, tol: float = 0.05) -> dict:
    """Per-drum precision/recall/F1 with a ±tol second matching window."""
    out = {}
    drums = sorted({d for _, d in truth_hits})
    for drum in drums:
        ref = sorted(t for t, d in truth_hits if d == drum)
        est = sorted(t for t, d in detected_hits if d == drum)
        used = [False] * len(est)
        tp = 0
        for r in ref:
            best, best_dt = None, tol
            for j, e in enumerate(est):
                if not used[j] and abs(e - r) <= best_dt:
                    best, best_dt = j, abs(e - r)
            if best is not None:
                used[best] = True
                tp += 1
        p = tp / len(est) if est else 0.0
        r = tp / len(ref) if ref else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        out[drum] = {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3),
                     "ref": len(ref), "est": len(est)}
    return out
