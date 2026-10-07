"""ffmpeg conversions: an MP3 to keep, and a mono WAV for analysis."""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import config

ANALYSIS_SR = 44100


def _ffmpeg(*args: str) -> None:
    cmd = [config.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()[-500:]}")


def to_mp3(src: Path, dst: Path, quality: int = 2) -> Path:
    """VBR MP3 (LAME -V2, ~190 kbps)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg("-i", str(src), "-vn", "-codec:a", "libmp3lame", "-q:a", str(quality), str(dst))
    return dst


def to_wav(src: Path, dst: Path, sr: int = ANALYSIS_SR) -> Path:
    """Mono 16-bit PCM at the analysis sample rate."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg("-i", str(src), "-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(dst))
    return dst


def duration(path: Path) -> float:
    import soundfile as sf

    info = sf.info(str(path))
    return info.frames / info.samplerate


def has_mp3_encoder() -> bool:
    proc = subprocess.run(
        [config.ffmpeg_exe(), "-hide_banner", "-encoders"], capture_output=True, text=True
    )
    return "libmp3lame" in proc.stdout
