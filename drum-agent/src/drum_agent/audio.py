"""ffmpeg conversions (an MP3 to keep, a mono WAV for analysis) and input checks."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import config

ANALYSIS_SR = 44100
SUPPORTED = {".wav", ".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".aif", ".aiff", ".wma", ".mp4",
             ".webm", ".mkv", ".mov"}
MAX_BYTES = 1024 * 1024 * 1024
MIN_SECONDS, MAX_SECONDS = 2.0, 30 * 60
SILENT_RMS_DB = -55.0


class AudioError(ValueError):
    """A problem with the input audio, worded for the user."""


def inspect(path: Path) -> dict:
    """Check a user's audio file before analysis: raises AudioError with a plain reason.

    Returns {"codec", "sample_rate", "channels", "duration_s", "warnings"} from ffmpeg's
    stream description (works with the bundled ffmpeg, which has no ffprobe).
    """
    path = Path(path)
    if not path.exists():
        raise AudioError(f"{path} does not exist.")
    if not path.is_file():
        raise AudioError(f"{path} is a folder, not an audio file.")
    size = path.stat().st_size
    if size == 0:
        raise AudioError(f"{path.name} is empty (0 bytes).")
    if size > MAX_BYTES:
        raise AudioError(f"{path.name} is {size / 1e9:.1f} GB; use a file under 1 GB (a normal song is 3-15 MB).")
    warnings = []
    if path.suffix.lower() not in SUPPORTED:
        warnings.append(f"unusual file type '{path.suffix}': reading it by content")
    proc = subprocess.run([config.ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    text = proc.stderr
    stream = re.search(r"Stream #\S+.*?: Audio: ([^,\s]+)[^\n]*?(\d+) Hz, ([^,\n]+)", text)
    if not stream:
        reason = "it has no audio stream" if "Stream #" in text else "ffmpeg cannot read it (damaged or not audio)"
        raise AudioError(f"{path.name} cannot be used: {reason}.")
    dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", text)
    seconds = int(dur[1]) * 3600 + int(dur[2]) * 60 + float(dur[3]) if dur else None
    if seconds is not None and seconds < MIN_SECONDS:
        raise AudioError(f"{path.name} is {seconds:.1f} s long; at least {MIN_SECONDS:g} s is needed for a beat grid.")
    if seconds is not None and seconds > MAX_SECONDS:
        raise AudioError(f"{path.name} is {seconds / 60:.0f} minutes long; split it (the limit is "
                         f"{MAX_SECONDS / 60:.0f} minutes).")
    rate = int(stream[2])
    if rate < 22050:
        warnings.append(f"low sample rate {rate} Hz: cymbal detail above {rate // 2} Hz is missing")
    bitrate = re.search(r"Audio: [^\n]*?(\d+) kb/s", text)
    if bitrate and int(bitrate[1]) < 96 and stream[1] not in ("pcm_s16le", "pcm_s24le", "flac", "alac"):
        warnings.append(f"low bit rate {bitrate[1]} kb/s: drum attacks may be smeared")
    return {"codec": stream[1], "sample_rate": rate, "channels": stream[3].strip(), "duration_s": seconds,
            "warnings": warnings}


def check_levels(y, warnings: list[str]) -> None:
    """Raise for a silent recording; warn about heavy clipping. y: float samples."""
    import numpy as np

    if y.size == 0:
        raise AudioError("The audio decoded to no samples.")
    rms = float(np.sqrt(np.mean(np.square(y, dtype=np.float64))))
    if rms <= 0 or 20 * np.log10(rms) < SILENT_RMS_DB:
        raise AudioError("The recording is silent (or nearly): there is nothing to transcribe.")
    clipped = float(np.mean(np.abs(y) >= 0.999))
    if clipped > 0.001:
        warnings.append(f"{clipped * 100:.1f}% of samples are clipped: drum attacks may blur together")


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
