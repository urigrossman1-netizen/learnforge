"""Drum transcription with signal processing only (no model weights to download).

Pipeline: soft harmonic/percussive separation -> beat tracking -> decompose
the attack spectrum of every frame into kick / snare / hi-hat templates (a
small non-negative factorisation whose templates adapt to the recording) ->
threshold and snap activation peaks to a beat-relative grid -> cymbal sustain check (hi-hat vs
crash) -> downbeat phase -> bars -> grooves, sections and fills.

On a full mix, bass guitar and toms can leak into kick/snare and ghost notes
are often missed. Passing an isolated drum stem (`is_drum_stem`) skips the
separation step and gives cleaner results.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import maximum_filter1d, median_filter

HOP = 256
N_FFT = 2048
SR = 44100
N_MELS = 96

DRUMS = ("kick", "snare", "hihat", "crash")
GM_NOTES = {"kick": 36, "snare": 38, "hihat": 42, "crash": 49}


@dataclass
class Options:
    bpm: float | None = None
    beats_per_bar: int = 4
    subdivision: int = 4
    is_drum_stem: bool = False
    # Move bar lines by this many beats when the detected "1" is wrong.
    shift_beats: int = 0


# Per drum: which spectrogram its activations come from, and the hit threshold.
# Tuned on MDB Drums (23 annotated real recordings, full mixes and drum stems):
# the kick is detected best on the unseparated spectrum (a percussive split
# weakens its body); snare and hi-hat on the soft percussive part.
#   ("full", "p95", 0.6): hit if >= 0.6 x the 95th percentile of the curve's peaks
#   ("perc", "abs", 0.5): hit if >= 0.5 x the curve's 99.5th percentile
DETECT = {"kick": ("full", "p95", 0.6), "snare": ("perc", "abs", 0.5), "hihat": ("perc", "abs", 0.2)}


MIN_DURATION = 2.0  # seconds; shorter clips cannot carry a beat grid
# Cost of restarting the bar count (after a stop, a dropped beat or a tempo
# break). Higher = trust one global bar phase more.
RESET_COST = 12.0


def transcribe(y: np.ndarray, sr: int = SR, opts: Options | None = None) -> dict:
    import librosa

    opts = opts or Options()
    if sr != SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
        sr = SR
    duration = len(y) / sr
    if duration < MIN_DURATION:
        raise ValueError(f"Audio is {duration:.1f} s long; at least {MIN_DURATION:g} s is needed to chart it.")

    # One float32 magnitude spectrogram feeds everything; the complex STFT is
    # dropped at once (it and a complex HPSS dominated memory on long songs).
    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP))
    if opts.is_drum_stem:
        harm_chroma, P = None, S
    else:
        harm_chroma, P = _hpss(S, sr)
    mel_full = _mel(S, sr)
    mel_perc = mel_full if P is S else _mel(P, sr)
    act_full, times = _activations(mel_full, sr)
    acts = {"full": act_full, "perc": act_full if P is S else _activations(mel_perc, sr)[0]}

    beat_times, bpm = _beats(mel_perc, _beat_envelope(acts), sr, duration, opts)
    sub, bpb = opts.subdivision, opts.beats_per_bar
    grid = _grid(beat_times, sub)
    step_dur = float(np.median(np.diff(grid)))

    hits = {}
    for k, name in enumerate(("kick", "snare", "hihat")):
        source, rule, thr = DETECT[name]
        hits[name] = _grid_hits(acts[source][k], times, grid, step_dur, rule, thr)
    hits.update(_split_cymbals(hits.pop("hihat"), grid, _band_energy(S, sr, 10000, 16000), times))

    chord_change = _beat_change(harm_chroma, beat_times, sr) if harm_chroma is not None else None
    del harm_chroma, P
    mfcc = librosa.feature.mfcc(S=librosa.power_to_db(mel_full), n_mfcc=13)
    timbre_change = _beat_change(mfcc, beat_times, sr, standardize=True)
    positions, resets = _downbeats(hits, len(beat_times), bpb, sub, chord_change, timbre_change)
    positions = (positions - opts.shift_beats) % bpb
    bars = _bars(hits, beat_times, positions, resets, bpb, sub)
    _complete_hats(bars, bpb, sub)
    bar_feats = _bar_features(S, mfcc, sr, bars)
    grooves, bar_groove = _grooves(bars)
    sections = _sections(bars, bar_groove, bar_feats, bpb * sub)
    _mark_fills(bars, bar_groove, sections)

    bpms = 60.0 / np.diff(beat_times)
    return {
        "tempo": {
            "bpm": round(float(bpm), 1),
            "bpm_min": round(float(np.percentile(bpms, 5)), 1),
            "bpm_max": round(float(np.percentile(bpms, 95)), 1),
            "beats_per_bar": bpb,
            "subdivision": sub,
            "first_downbeat_s": round(bars[0]["start_s"], 3) if bars else None,
            "bar_restarts": len(resets),
        },
        "duration_s": round(duration, 2),
        "instruments": list(DRUMS),
        "grooves": grooves,
        "sections": sections,
        "bars": bars,
        "notes": _caveats(opts, bool(resets)),
    }


# --------------------------------------------------------------------------- onsets


def _templates(mel_f):
    """Generic attack spectra for kick, snare and hi-hat, with hard frequency limits."""
    lf = np.log2(mel_f)

    def bump(center, sd):
        return np.exp(-0.5 * ((lf - np.log2(center)) / sd) ** 2)

    ramp = lambda lo, width: np.clip((lf - np.log2(lo)) / width, 0, 1)  # noqa: E731
    kick = (bump(60, 0.6) + 0.03) * (mel_f < 6000)
    snare = 0.4 * bump(200, 0.4) + ramp(800, 1.0) * (1 - ramp(12000, 0.7)) + 0.02
    hat = (ramp(5000, 0.6) + 0.01) * (mel_f > 4000)
    W = np.stack([kick, snare, hat], 1)
    mask = (W > 0).astype(float)
    return W / W.sum(0), mask


def _hpss(S, sr, kernel=31, chunk=4096):
    """Soft harmonic/percussive split (as librosa's hpss, margin 1), in float32 chunks.

    Returns (chroma of the harmonic part, percussive magnitude). Only the
    harmonic chroma is kept, so memory stays near one extra spectrogram.
    """
    import librosa

    fb = librosa.filters.chroma(sr=sr, n_fft=N_FFT, tuning=0.0).astype(np.float32)
    P = np.empty_like(S)
    chroma = np.empty((fb.shape[0], S.shape[1]), dtype=np.float32)
    half, n = kernel // 2, S.shape[1]
    for a in range(0, n, chunk):
        b = min(n, a + chunk)
        lo, hi = max(0, a - half), min(n, b + half)
        harm = median_filter(S[:, lo:hi], size=(1, kernel), mode="reflect")[:, a - lo : b - lo] ** 2
        perc = median_filter(S[:, a:b], size=(kernel, 1), mode="reflect") ** 2
        total = harm + perc
        mask = np.divide(perc, total, out=np.full_like(perc, 0.5), where=total > 1e-20)
        P[:, a:b] = S[:, a:b] * mask
        chroma[:, a:b] = fb @ ((S[:, a:b] - P[:, a:b]) ** 2)
    return chroma / (chroma.max(axis=0, keepdims=True) + 1e-9), P


def _mel(S, sr):
    """96-band mel power spectrogram (20 Hz - 16 kHz) of a magnitude spectrogram."""
    import librosa

    return librosa.feature.melspectrogram(S=S**2, sr=sr, n_mels=N_MELS, fmin=20, fmax=16000)


def _activations(mel, sr, adapt_rounds=4):
    """Kick/snare/hi-hat activation curves from the positive spectral flux.

    Flux (rather than the spectrogram) keeps only attacks, so ringing cymbals
    and sustained notes do not smear the activations. Templates are re-fitted
    to frames where one drum clearly dominates, half-way back to the prior.
    """
    import librosa

    mel_f = librosa.mel_frequencies(n_mels=N_MELS + 2, fmin=20, fmax=16000)[1:-1]
    A = np.sqrt(mel / (mel.max() + 1e-12))
    ref = maximum_filter1d(A, size=3, axis=0)
    F = np.zeros_like(A)
    F[:, 2:] = np.maximum(0.0, A[:, 2:] - ref[:, :-2])

    W0, mask = _templates(mel_f)
    W = W0.copy()
    for round_ in range(adapt_rounds + 1):
        H = _nnls_mu(W, F)
        if round_ == adapt_rounds:
            break
        parts = W[:, :, None] * H[None]
        total = parts.sum(axis=(0, 1)) + 1e-12
        cols = []
        for k in range(W.shape[1]):
            share = parts[:, k].sum(0) / total
            strong = (H[k] > np.percentile(H[k], 97)) & (share > 0.6)
            if strong.sum() >= 5:
                w = F[:, strong].mean(1) * mask[:, k]
                w = 0.5 * w / (w.sum() + 1e-12) + 0.5 * W0[:, k]
            else:
                w = W[:, k]
            cols.append(w / w.sum())
        W = np.stack(cols, 1)
    times = librosa.frames_to_time(np.arange(F.shape[1]), sr=sr, hop_length=HOP)
    return H, times


def _nnls_mu(W, F, iters=80):
    """Non-negative least squares for all frames at once (multiplicative updates)."""
    H = np.full((W.shape[1], F.shape[1]), F.mean() + 1e-6)
    WtF, WtW = W.T @ F, W.T @ W
    for _ in range(iters):
        H *= WtF / (WtW @ H + 1e-12)
    return H


def _band_energy(S, sr, lo, hi):
    """Power per frame between lo and hi Hz, from a magnitude spectrogram."""
    freqs = np.linspace(0, sr / 2, S.shape[0])
    return (S[(freqs >= lo) & (freqs <= hi)] ** 2).sum(axis=0)


def _beat_envelope(acts):
    """Onset strength for beat tracking: kick and snare attacks, little hi-hat.

    Off-beat hi-hats (disco, funk) otherwise pull the tracker onto the "&".
    """

    def unit(x):
        return x / (np.percentile(x, 99) + 1e-9)

    return unit(acts["full"][0]) + unit(acts["perc"][1]) + 0.25 * unit(acts["perc"][2])


def _beats(mel_perc, drum_env, sr, duration, opts):
    """Tempo from all percussive onsets (robust), beat positions from kick/snare."""
    import librosa

    tempo = opts.bpm or _tempo(librosa.onset.onset_strength(S=librosa.power_to_db(mel_perc), sr=sr), sr)
    _, beats = librosa.beat.beat_track(
        onset_envelope=drum_env, sr=sr, hop_length=HOP, tightness=200, bpm=tempo, units="time"
    )
    beats = np.asarray(beats, dtype=float)
    period = float(np.median(np.diff(beats))) if beats.size >= 4 else 60.0 / tempo
    if beats.size < 4:
        beats = np.arange(0.0, max(duration, 2 * period), period)
    # Extend the beat grid to cover the whole file so intro/outro hits get a slot.
    head = np.arange(beats[0] - period, -period, -period)[::-1]
    tail = np.arange(beats[-1] + period, duration + period, period)
    beats = np.concatenate([head, beats, tail])
    return beats, 60.0 / period


def _tempo(onset_env, sr, start_bpm=110.0, chunk=1024):
    """librosa's global tempo estimate, with its tempogram averaged chunk by chunk.

    Identical to librosa.feature.tempo (8 s autocorrelation windows, mean over
    the song, log-normal prior), but never holds the whole tempogram, which
    needs over 1 GB for a few minutes of audio.
    """
    import librosa
    from scipy.signal import get_window

    win = int(librosa.time_to_frames(8.0, sr=sr, hop_length=HOP))
    n = len(onset_env)
    padded = np.pad(onset_env, (win // 2, win // 2), mode="linear_ramp", end_values=(0, 0))
    window = get_window("hann", win, fftbins=True)[:, None]
    total = np.zeros(win)
    for a in range(0, n, chunk):
        b = min(n, a + chunk)
        frames = librosa.util.frame(padded[a : b + win - 1], frame_length=win, hop_length=1)
        ac = librosa.autocorrelate(frames * window, axis=0)
        total += librosa.util.normalize(ac, norm=np.inf, axis=0).sum(axis=1)
    tg = (total / n)[:, None]
    tempo = float(np.atleast_1d(librosa.feature.tempo(tg=tg, sr=sr, hop_length=HOP, start_bpm=start_bpm))[0])
    return tempo if np.isfinite(tempo) and tempo > 0 else 120.0


def _grid(beat_times, sub):
    pts = [np.linspace(a, b, sub, endpoint=False) for a, b in zip(beat_times[:-1], beat_times[1:])]
    return np.concatenate(pts + [beat_times[-1:]])


def _grid_hits(env, times, grid, step_dur, rule, thr):
    """Peak-pick an activation curve, keep strong peaks, snap them to the grid.

    Returns {grid index: velocity}; a typical (median) hit has velocity 0.7,
    capped at 1.
    """
    import librosa

    norm = env / (np.percentile(env, 99.5) + 1e-9)
    peaks = librosa.util.peak_pick(
        norm, pre_max=3, post_max=3, pre_avg=10, post_avg=10, delta=0.02, wait=3
    )
    if peaks.size == 0:
        return {}
    strengths = norm[peaks]
    ref = np.percentile(strengths, 95) if rule == "p95" else 1.0
    keep = strengths >= thr * ref
    if not keep.any():
        return {}
    # 0.7 = a typical hit; >= 0.9 is an accent (1.3x typical), < 0.35 a ghost note.
    vel_ref = np.median(strengths[keep]) / 0.7
    tol = min(0.45 * step_dur, 0.06)
    slots: dict[int, float] = {}
    for t, s in zip(times[peaks][keep], strengths[keep]):
        g = int(np.searchsorted(grid, t))
        i = min((j for j in (g - 1, g) if 0 <= j < grid.size), key=lambda j: abs(grid[j] - t))
        if abs(grid[i] - t) > tol:
            continue
        vel = min(float(s / vel_ref), 1.0)
        if vel > slots.get(i, 0.0):
            slots[i] = vel
    return slots


def _split_cymbals(cym, grid, hi_energy, times):
    """Hi-hat vs crash: a crash leaves a loud wash for most of a second.

    The wash is the noise floor (10th percentile) 0.4-0.9 s after the hit,
    which ignores the next hi-hat or snare stroke. It must reach a quarter of
    a typical cymbal hit's peak and clearly exceed the floor before the hit,
    so a steady ride/open-hat wash or a snare roll does not count.
    """
    fps = 1.0 / (times[1] - times[0])
    pre0, pre1, post0, post1 = (int(x * fps) for x in (0.6, 0.05, 0.4, 0.9))
    frames = {i: int(np.searchsorted(times, grid[i])) for i in cym}
    peaks = [hi_energy[f : f + 6].max() for f in frames.values() if f + 1 < hi_energy.size]
    typical = float(np.median(peaks)) if peaks else 0.0
    out = {"hihat": {}, "crash": {}}
    for i, vel in cym.items():
        f0 = frames[i]
        before = hi_energy[max(0, f0 - pre0) : max(0, f0 - pre1)]
        after = hi_energy[f0 + post0 : f0 + post1]
        crash = False
        if after.size >= 5 and vel >= 0.5:
            floor_before = np.percentile(before, 10) if before.size >= 5 else 0.0
            floor_after = np.percentile(after, 10)
            crash = floor_after > 0.25 * typical and floor_after > 3 * floor_before
        out["crash" if crash else "hihat"][i] = vel
    return out


# --------------------------------------------------------------------------- bars


def _downbeats(hits, n_beats, bpb, sub, chord_change=None, timbre_change=None, reset_cost=RESET_COST):
    """Bar position (0 = beat 1) of every beat, decoded with a small Viterbi pass.

    Evidence for "this beat is 1": kick and crash on it, little snare, a chord
    change and above all a timbre change (new phrases and sections start on
    downbeats; this settles the common 1-vs-3 ambiguity of rock/pop grooves:
    16 of 17 correctly tracked MDB Drums songs, against 11 with drum and chord
    cues alone). In 4/4 the snare backs beats 2 and 4. The count normally
    advances one beat at a time; restarting it costs `reset_cost`, so a stop
    or tempo break realigns the bar lines instead of shifting all later bars.
    Returns (positions, set of beat indices where the count restarted).
    """

    def on_beat(name):
        a = np.zeros(n_beats)
        for i, v in hits.get(name, {}).items():
            if i % sub == 0 and i // sub < n_beats:
                a[i // sub] = v
        return a

    kick, snare, crash = on_beat("kick"), on_beat("snare"), on_beat("crash")
    chord = chord_change if chord_change is not None else np.zeros(n_beats)
    timbre = timbre_change if timbre_change is not None else np.zeros(n_beats)
    emit = np.zeros((n_beats, bpb))
    emit[:, 0] = kick + 2 * crash - 0.5 * snare + 0.5 * chord + 4 * timbre
    if bpb == 4:
        emit[:, 1] = emit[:, 3] = snare - 0.5 * kick

    prev = (np.arange(bpb) - 1) % bpb
    score = emit[0].copy()
    back = np.zeros((n_beats, bpb), dtype=int)
    for b in range(1, n_beats):
        stay = score[prev]
        best = int(np.argmax(score))
        jump = score[best] - reset_cost
        back[b] = np.where(jump > stay, best, prev)
        score = emit[b] + np.maximum(stay, jump)
    pos = np.zeros(n_beats, dtype=int)
    pos[-1] = int(np.argmax(score))
    for b in range(n_beats - 1, 0, -1):
        pos[b - 1] = back[b, pos[b]]
    resets = {b for b in range(1, n_beats) if pos[b] != (pos[b - 1] + 1) % bpb}
    return pos, resets


def _beat_change(feat, beat_times, sr, standardize=False):
    """How far a frame-level feature (e.g. MFCC) jumps from one beat to the next."""
    import librosa

    frames = librosa.time_to_frames(np.clip(beat_times, 0, None), sr=sr, hop_length=HOP)
    frames = np.clip(frames, 0, feat.shape[1] - 1)
    ends = np.append(frames[1:], feat.shape[1])
    sync = np.stack([feat[:, a : max(b, a + 1)].mean(1) for a, b in zip(frames, ends)], axis=1)
    if standardize:
        sync = (sync - sync.mean(1, keepdims=True)) / (sync.std(1, keepdims=True) + 1e-9)
    change = np.zeros(sync.shape[1])
    change[1:] = np.linalg.norm(np.diff(sync, axis=1), axis=0)
    return change / (np.percentile(change, 95) + 1e-9)


def _bars(hits, beat_times, positions, resets, bpb, sub):
    """Group grid hits into bars. Steps are metrical: step 0 is always beat 1.

    A bar starts at every beat 1 and wherever the count restarted. A pickup or
    a bar cut short by a restart is "partial": its missing beats stay empty.
    """
    steps = bpb * sub
    occupied = [i for h in hits.values() for i in h]
    if not occupied:
        return []
    first_beat, last_beat = min(occupied) // sub, max(occupied) // sub
    n = len(beat_times)
    period = float(np.median(np.diff(beat_times)))
    starts = [b for b in range(n) if b == 0 or positions[b] == 0 or b in resets]
    bars = []
    for k, b0 in enumerate(starts):
        b1 = starts[k + 1] if k + 1 < len(starts) else n
        if b1 <= first_beat or b0 > last_beat:
            continue
        offset = int(positions[b0]) * sub
        bar_hits = {name: [] for name in ("kick", "snare", "hihat", "crash")}
        for g in range(b0 * sub, min(b1 - b0, bpb - positions[b0]) * sub + b0 * sub):
            for name in bar_hits:
                if g in hits.get(name, {}):
                    bar_hits[name].append([offset + g - b0 * sub, round(hits[name][g], 2)])
        start = float(beat_times[b0] - positions[b0] * period)
        full = positions[b0] == 0 and b1 - b0 == bpb
        end = float(beat_times[b1]) if full and b1 < n else start + bpb * period
        bar = {"index": len(bars) + 1, "start_s": round(start, 3), "end_s": round(end, 3), "hits": bar_hits}
        if not full and b1 < n:
            bar["partial"] = {"first_beat": int(positions[b0]) + 1, "beats": int(min(b1 - b0, bpb - positions[b0]))}
            if bars and start < bars[-1]["end_s"]:
                # A restart can put the virtual start of this bar before the end of the
                # previous one; keep that for hit timing, show the real start.
                bar["grid_start_s"] = bar["start_s"]
                bar["start_s"] = round(float(beat_times[b0]), 3)
        bars.append(bar)
    return bars


def _bar_features(S, mfcc, sr, bars):
    """Per-bar harmony/timbre/loudness vectors used to find section boundaries."""
    import librosa

    if not bars:
        return np.zeros((0, 26))
    chroma = librosa.feature.chroma_stft(S=S**2, sr=sr, hop_length=HOP, tuning=0.0)
    rms = librosa.feature.rms(S=S, frame_length=N_FFT, hop_length=HOP)[0]
    edges = [b["start_s"] for b in bars] + [bars[-1]["end_s"]]
    frames = librosa.time_to_frames(np.clip(edges, 0, None), sr=sr, hop_length=HOP)
    frames = np.clip(frames, 0, S.shape[1] - 1)
    feats = []
    for bar, a, b in zip(bars, frames[:-1], frames[1:]):
        b = max(b, a + 1)
        level = float(rms[a:b].mean())
        bar["energy_db"] = round(20 * np.log10(level + 1e-9), 1)
        feats.append(np.concatenate([chroma[:, a:b].mean(1), mfcc[1:, a:b].mean(1) / 20, [np.log1p(100 * level)]]))
    return np.array(feats)


# --------------------------------------------------------------------------- structure


def _pattern(bar):
    """Binary groove signature: kick, snare and time-keeping cymbal (hat or ride)."""
    steps = {name: {s for s, _ in bar["hits"].get(name, [])} for name in ("kick", "snare", "hihat", "crash")}
    return steps["kick"], steps["snare"], steps["hihat"]


def _distance(a, b, w=(2.0, 2.0, 1.0)):
    num = sum(wi * len(x ^ y) for wi, x, y in zip(w, a, b))
    den = sum(wi * len(x | y) for wi, x, y in zip(w, a, b))
    return num / den if den else 0.0


def _grooves(bars, tau=0.3):
    """Greedy clustering of bar patterns into grooves A, B, C... (most common first)."""
    protos: list[list] = []  # [pattern, member indices]
    assign = []
    for i, bar in enumerate(bars):
        p = _pattern(bar)
        if not any(p):
            assign.append(None)
            continue
        best = min(range(len(protos)), key=lambda j: _distance(p, protos[j][0]), default=None)
        if best is not None and _distance(p, protos[best][0]) <= tau:
            protos[best][1].append(i)
            assign.append(best)
        else:
            protos.append([p, [i]])
            assign.append(len(protos) - 1)

    order = sorted(range(len(protos)), key=lambda j: -len(protos[j][1]))
    names = {j: _letter(n) for n, j in enumerate(order)}
    grooves = {}
    for j in order:
        members = protos[j][1]
        grooves[names[j]] = {
            "bars": len(members),
            "bar_indices": [bars[m]["index"] for m in members],
            "pattern": _consensus([bars[m] for m in members]),
        }
    bar_groove = [names[a] if a is not None else None for a in assign]
    for bar, g in zip(bars, bar_groove):
        bar["groove"] = g
    return grooves, bar_groove


def _letter(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _consensus(members):
    """Steps hit in at least half of the member bars, per instrument."""
    out = {}
    for name in ("kick", "snare", "hihat"):
        counts: dict[int, int] = {}
        for bar in members:
            for s, _ in bar["hits"].get(name, []):
                counts[s] = counts.get(s, 0) + 1
        out[name] = sorted(s for s, c in counts.items() if c * 2 >= len(members))
    return out


def _sections(bars, bar_groove, feats, steps, min_len=4):
    """Section boundaries from a checkerboard novelty curve over per-bar features.

    Features: harmony, timbre, loudness and the bar's drum pattern, each group
    standardized and given equal weight, plus a bonus for a crash on beat 1.
    """
    n = len(bars)
    if n == 0:
        return []
    drums = np.zeros((n, 3 * steps))
    for j, bar in enumerate(bars):
        for k, name in enumerate(("kick", "snare", "hihat")):
            for st, _ in bar["hits"][name]:
                drums[j, k * steps + st] = 1.0
    groups = [feats[:, :12], feats[:, 12:-1], feats[:, -1:], drums]
    X = np.hstack([_standardize(g) for g in groups])
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9

    # Novelty is measured over full bars only: the silence of a stop or a
    # pickup would otherwise look like a section change on both sides of it.
    full = [j for j in range(n) if not bars[j].get("partial")] or list(range(n))
    m = len(full)
    ssm = X[full] @ X[full].T
    k = 4
    novelty = np.zeros(m)
    for i in range(2, m - 1):
        w = min(k, i, m - i)
        a, b = ssm[i - w : i, i - w : i], ssm[i : i + w, i : i + w]
        c = ssm[i - w : i, i : i + w]
        novelty[i] = ((a.mean() + b.mean()) / 2 - c.mean()) * (w / k) ** 0.5
    novelty /= novelty.max() + 1e-9
    crash_on_one = np.array([any(st == 0 for st, _ in bars[j]["hits"]["crash"]) for j in full], float)
    score = novelty + 0.3 * crash_on_one

    # The music restarts after a stop: a section starts at the first full bar.
    picked = [0] + [i for i in range(1, m) if full[i] - full[i - 1] > 1]
    for i in sorted(range(1, m), key=lambda i: -score[i]):
        if score[i] < 0.4:
            break
        if all(abs(i - b) >= min_len for b in picked) and m - i >= 2 and _changes_at(i, full, bars, feats, crash_on_one):
            picked.append(i)
    bounds = sorted({0} | {full[i] for i in picked if i > 0}) + [n]

    sections, means = [], []
    for si, (a, b) in enumerate(zip(bounds[:-1], bounds[1:])):
        gs = [g for g in bar_groove[a:b] if g]
        main = max(set(gs), key=gs.count) if gs else None
        whole = [j for j in range(a, b) if not bars[j].get("partial")] or list(range(a, b))
        means.append(X[whole].mean(0))
        sections.append(
            {
                "index": si + 1,
                "first_bar": bars[a]["index"],
                "last_bar": bars[b - 1]["index"],
                "bars": b - a,
                "start_s": bars[a]["start_s"],
                "end_s": bars[b - 1]["end_s"],
                "groove": main,
                "energy_db": round(float(np.mean([bars[j]["energy_db"] for j in whole])), 1),
                "crash_bars": [bars[j]["index"] for j in range(a, b) if bars[j]["hits"]["crash"]],
            }
        )
    # Sections that sound alike share a letter (A, B, A ...).
    # Same main groove at a similar level, or very similar overall sound.
    labels: list[tuple[np.ndarray, dict, str]] = []
    for sec, m in zip(sections, means):
        m = m / (np.linalg.norm(m) + 1e-9)

        def alike(g, other):
            same_groove = sec["groove"] and sec["groove"] == other["groove"]
            close = abs(sec["energy_db"] - other["energy_db"]) < 3.0
            return (same_groove and close) or float(m @ g) > 0.8

        match = next((lab for g, other, lab in labels if alike(g, other)), None)
        if match is None:
            match = _letter(len(labels))
            labels.append((m, sec, match))
        sec["label"] = match
    for sec in sections:
        for j in range(sec["first_bar"] - 1, sec["last_bar"]):
            bars[j]["section"] = sec["index"]
    return sections


HARMONY_SHIFT = 0.08  # cosine distance between mean chroma of the 4 bars before/after


def _changes_at(i, full, bars, feats, crash_on_one, w=4):
    """Does something concrete change at full bar i? Novelty alone is relative to
    the song's largest change, so a uniform loop would otherwise get sections."""
    before, after = full[max(0, i - w) : i], full[i : i + w]

    def main_groove(idx):
        gs = [bars[j].get("groove") for j in idx if bars[j].get("groove")]
        return max(set(gs), key=gs.count) if gs else None

    if crash_on_one[i] or main_groove(before) != main_groove(after):
        return True
    level = [bars[j]["energy_db"] for j in before], [bars[j]["energy_db"] for j in after]
    if abs(np.mean(level[1]) - np.mean(level[0])) >= 1.5:
        return True
    ca, cb = feats[before, :12].mean(0), feats[after, :12].mean(0)
    return 1 - float(ca @ cb) / (np.linalg.norm(ca) * np.linalg.norm(cb) + 1e-9) >= HARMONY_SHIFT


def _standardize(g):
    g = g - g.mean(0)
    std = g.std(0)
    g = g / np.where(std > 1e-9, std, 1.0)
    return g / np.sqrt(g.shape[1])


def _complete_hats(bars, bpb, sub):
    """Restore hi-hats masked by a simultaneous snare in an otherwise regular pattern.

    When a bar's hats sit on (nearly) every 16th, 8th or quarter note and the
    only gaps fall on snare hits, the drummer almost certainly kept the hat
    going; the snare simply hid it. Restored steps are listed under "inferred".
    """
    steps = bpb * sub
    spacings = [d for d in range(1, sub + 1) if sub % d == 0]
    for bar in bars:
        hats = {st: v for st, v in bar["hits"]["hihat"]}
        if len(hats) < 3 or bar.get("partial"):
            continue
        snares = {st for st, _ in bar["hits"]["snare"]}
        for d in spacings:  # finest grid first
            slots = set(range(0, steps, d))
            if sum(1 for st in hats if st % d) > 1 or len(slots & set(hats)) < 0.6 * len(slots):
                continue  # hats do not follow this grid
            missing = slots - set(hats)
            if missing and missing <= snares:
                vel = round(float(np.median(list(hats.values()))), 2)
                hats.update({st: vel for st in missing})
                bar["hits"]["hihat"] = sorted([st, v] for st, v in hats.items())
                bar["inferred"] = {"hihat": sorted(missing)}
            break


def _mark_fills(bars, bar_groove, sections):
    """A bar that breaks its section's groove at a phrase end (every 4 bars) is a fill."""
    for s in sections:
        s["fills"] = []
        for j in range(s["first_bar"] - 1, s["last_bar"]):
            bar = bars[j]
            pos = j - (s["first_bar"] - 1)
            differs = bar_groove[j] is not None and bar_groove[j] != s["groove"]
            phrase_end = (pos + 1) % 4 == 0 or j == s["last_bar"] - 1
            bar["fill"] = bool(differs and phrase_end)
            if bar["fill"]:
                s["fills"].append(bar["index"])


def _caveats(opts, restarted=False):
    notes = [
        "Automatic transcription: verify by ear before using the chart.",
        "Toms are not separated from snare/kick; fills may show tom hits as snare or kick.",
        "Ghost notes and hi-hat openings are often missed.",
    ]
    if not opts.is_drum_stem:
        notes.append(
            "Analyzed the full mix (harmonic/percussive separation only); bass guitar "
            "can add extra kick hits. Pass --drum-stem with an isolated drum track for better results."
        )
    if opts.beats_per_bar == 4:
        notes.append(
            "Time signature assumed 4/4; for 3/4 rerun with --beats-per-bar 3, "
            "for 6/8 with --beats-per-bar 2 --subdivision 3."
        )
    if restarted:
        notes.append("The bar count restarts at least once (a stop, break or tempo change); bars marked partial are incomplete.")
    return notes


def hit_times(result: dict) -> list[tuple[float, str]]:
    """(time_s, drum) for every hit, interpolating within each bar."""
    steps = result["tempo"]["beats_per_bar"] * result["tempo"]["subdivision"]
    out = []
    for bar in result["bars"]:
        start = bar.get("grid_start_s", bar["start_s"])
        dt = (bar["end_s"] - start) / steps
        for name, hs in bar["hits"].items():
            out.extend((start + s * dt, name) for s, _ in hs)
    return sorted(out)
