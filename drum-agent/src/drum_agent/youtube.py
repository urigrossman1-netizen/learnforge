"""YouTube search and audio download through the yt-dlp Python API."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from . import config

# Uploads whose audio is not the studio recording the chart should follow.
_BAD_WORDS = re.compile(
    r"\b(live|cover|karaoke|instrumental|remix|slowed|sped ?up|reverb|8d|"
    r"nightcore|reaction|lesson|tutorial|drumless|playthrough|bass boosted|"
    r"backing track|isolated|acoustic|demo)\b",
    re.I,
)
_GOOD_WORDS = re.compile(r"official (audio|video|music video)|provided to youtube", re.I)


class _QuietLogger:
    """yt-dlp prints errors to stderr even when quiet; they are raised as exceptions anyway."""

    def debug(self, msg):
        pass

    info = warning = error = debug


def _base_opts() -> dict:
    opts: dict = {
        "logger": _QuietLogger(),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "ffmpeg_location": config.ffmpeg_exe(),
    }
    deno = config.which("deno")
    if deno:
        # yt-dlp needs a JS runtime to solve YouTube's player challenges.
        opts["js_runtimes"] = {"deno": {"path": deno}}
    browser = config.cookies_from_browser()
    if browser:
        opts["cookiesfrombrowser"] = browser
    return opts


def search(query: str, n: int = 8) -> list[dict]:
    import yt_dlp

    opts = _base_opts() | {"extract_flat": "in_playlist", "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    results = []
    for e in info.get("entries") or []:
        if not e or not e.get("id"):
            continue
        results.append(
            {
                "id": e["id"],
                "title": e.get("title") or "",
                "channel": e.get("channel") or e.get("uploader") or "",
                "duration_s": e.get("duration"),
                "url": f"https://www.youtube.com/watch?v={e['id']}",
            }
        )
    return results


def rank(candidates: list[dict], ref_duration: float | None = None, query: str = "") -> list[dict]:
    """Order candidates by how likely they are the studio recording.

    Spotify's duration is the strongest signal: official audio uploads and
    auto-generated "Artist - Topic" tracks match it within a second or two.
    """
    def bad_words(text):
        return Counter(m.lower() for m in _BAD_WORDS.findall(text or ""))

    # A word in the song's own name ("Live Wire", "Cover Me") is allowed once;
    # a second "live" in "Live Wire (Live at ...)" is still penalised.
    wanted = bad_words(query)
    ranked = []
    for i, c in enumerate(candidates):
        score = -0.3 * i
        if c["channel"].endswith(" - Topic"):
            score += 4
        if _GOOD_WORDS.search(f"{c['title']} {c['channel']}"):
            score += 2
        extra = (bad_words(c["title"]) - wanted) + (bad_words(c["channel"]) - wanted)
        score -= 5 * sum(extra.values())
        if ref_duration and c.get("duration_s"):
            diff = abs(c["duration_s"] - ref_duration)
            score += 6 if diff <= 2 else 3 if diff <= 6 else -min(diff / 10, 8)
        ranked.append(c | {"score": round(score, 2)})
    return sorted(ranked, key=lambda c: c["score"], reverse=True)


def download_audio(
    url: str, out_dir: Path, basename: str, section: tuple[float, float] | None = None
) -> tuple[Path, dict]:
    """Download the best audio stream as-is (no re-encode); returns (file, info).

    `section` limits the download to (start, end) seconds, used by `doctor`.
    """
    import yt_dlp

    out_dir.mkdir(parents=True, exist_ok=True)
    opts = _base_opts() | {
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / f"{basename}.%(ext)s"),
        "overwrites": True,
    }
    if section:
        opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [section])
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(info["requested_downloads"][0]["filepath"])
    meta = {
        "id": info.get("id"),
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "duration_s": info.get("duration"),
        "url": info.get("webpage_url") or url,
        "acodec": info.get("acodec"),
        "abr": info.get("abr"),
    }
    return path, meta
