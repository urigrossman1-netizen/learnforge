"""Build the real-drum sample kit used for chart playback and test audio.

Source: Hydrogen's "GMRockKit", recordings of a 5-piece Pearl DX kit
(Glen MacArthur / Sebastian Moors, GPL-3.0-or-later):
https://github.com/hydrogen-music/hydrogen/tree/master/data/drumkits/GMRockKit

For every instrument we keep three velocity layers (soft, medium, hard), trim
the tail once it decays below -60 dB, add a 20 ms fade, and encode mono
96 kbps MP3 into src/drum_agent/drumchart/assets/kit/ with a kit.json manifest.

    uv run python tools/build_kit.py [cache_dir]     # needs network + ffmpeg (libmp3lame)
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import urllib.request
import wave
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

BASE = "https://raw.githubusercontent.com/hydrogen-music/hydrogen/master/data/drumkits/GMRockKit/"
NS = "{http://www.hydrogen-music.org/drumkit}"
OUT = Path(__file__).resolve().parents[1] / "src" / "drum_agent" / "drumchart" / "assets" / "kit"

# sample id -> Hydrogen instrument name
SAMPLES = {
    "kick": "Kick",
    "snare": "Snare",
    "rimshot": "Snare Rimshot",
    "stick": "Stick",
    "tom1": "Tom 1",
    "tom2": "Tom 2",
    "floor": "Floor Tom",
    "hat": "Hat Closed",
    "hat-open": "Hat Open",
    "hat-half": "Hat Semi-Open",
    "hat-pedal": "Hat Pedal",
    "ride": "Ride",
    "ride2": "Ride 2",
    "bell": "Bell",
    "crash": "Crash",
    "splash": "Splash",
    "cowbell": "Cowbell",
}
LAYERS = {"soft": 0.25, "medium": 0.6, "hard": 1.0}  # pick the recorded layer nearest these velocities


def fetch(url: str, dest: Path) -> Path:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as r:
            dest.write_bytes(r.read())
    return dest


def trim_encode(wav_path: Path, mp3_path: Path) -> float:
    with wave.open(str(wav_path)) as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise SystemExit(f"{wav_path.name}: expected 16-bit PCM")
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    peak = float(np.abs(x).max()) or 1.0
    win = int(sr * 0.005)
    env = np.array([np.abs(x[i : i + win]).max() for i in range(0, len(x), win)])
    idx = np.where(env > peak * 10 ** (-60 / 20))[0]
    y = x[: min(len(x), (int(idx[-1]) + 2) * win)].copy()
    fade = int(sr * 0.02)
    if len(y) > fade:
        y[-fade:] *= np.linspace(1, 0, fade)
    tmp = mp3_path.with_suffix(".tmp.wav")
    with wave.open(str(tmp), "wb") as ww:
        ww.setnchannels(1)
        ww.setsampwidth(2)
        ww.setframerate(sr)
        ww.writeframes((y * 32767).astype(np.int16).tobytes())
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(tmp), "-codec:a", "libmp3lame", "-b:a", "96k",
         "-ar", "44100", "-ac", "1", str(mp3_path)],
        check=True,
    )
    tmp.unlink()
    return len(y) / sr


def main() -> None:
    cache = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="gmrock-"))
    root = ET.parse(fetch(BASE + "drumkit.xml", cache / "drumkit.xml")).getroot()
    found = {}
    for ins in root.iter(NS + "instrument"):
        pl, pr = float(ins.find(NS + "pan_L").text), float(ins.find(NS + "pan_R").text)
        layers = sorted(
            (float(lay.find(NS + "max").text), lay.find(NS + "filename").text) for lay in ins.iter(NS + "layer")
        )
        found[ins.find(NS + "name").text] = {"pan": round((pr - pl) / (pr + pl), 3), "layers": layers}

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": "Hydrogen GMRockKit (5-piece Pearl DX, real recordings)",
        "license": "GPL-3.0-or-later",
        "authors": "Glen MacArthur / Sebastian Moors",
        "source": BASE,
        "samples": {},
    }
    total = 0
    for sid, hname in SAMPLES.items():
        info = found[hname]
        entry = {"pan": info["pan"], "layers": {}}
        for lname, target in LAYERS.items():
            vmax, fname = min(info["layers"], key=lambda lay: abs(lay[0] - target))
            wav = fetch(BASE + fname, cache / "wav" / fname)
            mp3 = OUT / f"{sid}-{lname}.mp3"
            seconds = trim_encode(wav, mp3)
            total += mp3.stat().st_size
            entry["layers"][lname] = {"file": mp3.name, "from": fname, "seconds": round(seconds, 3)}
        manifest["samples"][sid] = entry
        print(f"{sid:10s} <- {hname:14s} pan {info['pan']:+.2f}")
    (OUT / "kit.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"{len(SAMPLES)} samples x {len(LAYERS)} layers, {total // 1024} KB of MP3 in {OUT}")


if __name__ == "__main__":
    main()
