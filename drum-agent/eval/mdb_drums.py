"""Measure transcription accuracy on MDB Drums (23 real recordings with hand-annotated hits).

    uv run python eval/mdb_drums.py            # full mixes and drum stems, all songs
    uv run python eval/mdb_drums.py --mode mix --only Rock,Punk

The dataset (CC BY-NC-SA 4.0, ~330 MB of audio) is fetched once with a sparse
git checkout into .cache/mdb-drums. Scores: F1 with a ±50 ms window per
instrument, tempo within 4%, and the share of detected bar lines within 70 ms
of an annotated downbeat.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from drum_agent import config, synth, transcribe

REPO = "https://github.com/CarlSouthall/MDBDrums"
DATA = config.CACHE_DIR / "mdb-drums"
ROOT = DATA / "MDB Drums"
CLASSES = {"KD": "kick", "SD": "snare", "HH": "hihat"}


def fetch() -> None:
    if (ROOT / "annotations").exists():
        return
    DATA.parent.mkdir(parents=True, exist_ok=True)
    run = lambda *a: subprocess.run(["git", "-c", "gc.auto=0", *a], check=True)  # noqa: E731
    run("clone", "--depth", "1", "--filter=blob:none", "--no-checkout", REPO, str(DATA))
    run("-C", str(DATA), "sparse-checkout", "set", "--no-cone",
        "/MDB Drums/audio/full_mix/", "/MDB Drums/audio/drum_only/",
        "/MDB Drums/annotations/class/", "/MDB Drums/annotations/beats/")
    run("-C", str(DATA), "checkout")


def truth(song: str):
    hits = []
    for line in (ROOT / "annotations/class" / f"{song}_class.txt").read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] in CLASSES:
            hits.append((float(parts[0]), CLASSES[parts[1]]))
    beats = [tuple(map(float, line.split())) for line in
             (ROOT / "annotations/beats" / f"{song}_MIX.beats").read_text().splitlines() if line.strip()]
    return hits, beats


def evaluate(job):
    import librosa

    song, mode = job
    folder, suffix = ("full_mix", "MIX") if mode == "mix" else ("drum_only", "Drum")
    y, sr = librosa.load(ROOT / "audio" / folder / f"{song}_{suffix}.wav", sr=44100, mono=True)
    result = transcribe.transcribe(y, sr, transcribe.Options(is_drum_stem=mode == "stem"))
    hits, beats = truth(song)
    f1 = {d: s["f1"] for d, s in synth.score(hits, transcribe.hit_times(result)).items()}
    beat_t = np.array([b[0] for b in beats])
    true_bpm = 60 / np.median(np.diff(beat_t))
    downbeats = np.array([b[0] for b in beats if int(b[1]) == 1])
    starts = np.array([b["start_s"] for b in result["bars"]])
    starts = starts[(starts >= beat_t[0] - 0.1) & (starts <= beat_t[-1] + 0.1)]
    downbeat = float(np.mean([np.min(np.abs(downbeats - s)) < 0.07 for s in starts])) if starts.size else 0.0
    tempo_ok = abs(result["tempo"]["bpm"] / true_bpm - 1) < 0.04
    return song, mode, f1, tempo_ok, downbeat


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["mix", "stem", "both"], default="both")
    p.add_argument("--only", help="comma-separated substrings of song names")
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()
    fetch()
    songs = sorted(f.name.removesuffix("_MIX.wav") for f in (ROOT / "audio/full_mix").glob("*.wav"))
    if args.only:
        songs = [s for s in songs if any(o in s for o in args.only.split(","))]
    modes = ["mix", "stem"] if args.mode == "both" else [args.mode]
    with ProcessPoolExecutor(args.workers) as ex:
        rows = list(ex.map(evaluate, [(s, m) for s in songs for m in modes]))

    for song, mode, f1, tempo_ok, downbeat in rows:
        scores = " ".join(f"{d}={f1[d]:.2f}" for d in ("kick", "snare", "hihat") if d in f1)
        print(f"{song.removeprefix('MusicDelta_'):<12} {mode:<4} {scores:<36} tempo={'ok' if tempo_ok else 'x'} downbeat={downbeat:.2f}")
    for label, keep in (("non-jazz", lambda s: "Jazz" not in s), ("all", lambda s: True)):
        for mode in modes:
            sel = [r for r in rows if r[1] == mode and keep(r[0])]
            if not sel:
                continue
            mean = {d: np.mean([r[2][d] for r in sel if d in r[2]]) for d in ("kick", "snare", "hihat")}
            print(f"MEAN {label:<8} {mode:<4} n={len(sel):<2} " + " ".join(f"{d}={v:.2f}" for d, v in mean.items())
                  + f" tempo={np.mean([r[3] for r in sel]):.2f} downbeat={np.mean([r[4] for r in sel]):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
