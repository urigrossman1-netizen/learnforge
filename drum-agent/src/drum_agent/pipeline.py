"""Song lookup -> audio acquisition -> drum chart, writing everything under charts/<slug>/."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import audio, config, spotify, youtube


def resolve(
    query: str | None = None,
    *,
    title: str | None = None,
    artist: str | None = None,
    duration: float | None = None,
    url: str | None = None,
    use_spotify: bool = True,
    need_youtube: bool = True,
) -> dict:
    """Find Spotify metadata and the best-matching YouTube upload for a song.

    With need_youtube=False a failed YouTube search becomes a warning, so the
    Spotify result is still returned (used by `drum-agent search`).
    """
    meta: dict = {"query": query, "warnings": []}
    text = (query or " ".join(x for x in (artist, title) if x)).strip()
    if use_spotify and text:
        if spotify.has_credentials():
            try:
                tracks = spotify.search_tracks(text, title=title, artist=artist, limit=5)
                if tracks:
                    meta["spotify"] = tracks[0]
                    meta["spotify_alternatives"] = tracks[1:3]
                else:
                    meta["warnings"].append(f"Spotify found nothing for {text!r}.")
            except spotify.SpotifyError as e:
                meta["warnings"].append(f"Spotify lookup failed: {e}")
        else:
            meta["warnings"].append("Spotify credentials not set; using YouTube metadata only.")
    sp = meta.get("spotify") or {}
    meta["title"] = title or sp.get("title")
    meta["artist"] = artist or ", ".join(sp.get("artists") or []) or None
    meta["duration_s"] = duration or sp.get("duration_s")

    if url:
        meta["youtube"] = {"url": url}
    elif not text:
        raise ValueError("Nothing to search for: give a song name, --title/--artist, or --url.")
    else:
        yt_query = f"{meta['artist']} - {meta['title']}" if meta["title"] and meta["artist"] else text
        try:
            candidates = youtube.rank(youtube.search(yt_query), meta["duration_s"], yt_query)
            if not candidates:
                raise RuntimeError(f"YouTube search returned nothing for {yt_query!r}")
        except Exception as e:
            if need_youtube:
                raise
            meta["warnings"].append(f"YouTube search failed: {e}")
            candidates = []
        if candidates:
            meta["youtube"] = candidates[0]
            meta["youtube_alternatives"] = candidates[1:4]
            ref, got = meta["duration_s"], candidates[0].get("duration_s")
            if ref and got and abs(ref - got) > 6:
                meta["warnings"].append(
                    f"Best YouTube match is {got:.0f}s but Spotify says {ref:.0f}s; "
                    "it may be a different version. Pass --url to choose one."
                )
    name = f"{meta['artist']} - {meta['title']}" if meta["title"] and meta["artist"] else text
    # URL-only runs are named after the video once it is downloaded.
    meta["slug"] = config.slugify(name) if name else None
    return meta


def acquire(meta: dict) -> dict:
    """Download the YouTube audio, keep an MP3 in audio/, and an analysis WAV in .cache/."""
    url = (meta.get("youtube") or {}).get("url")
    if not url:
        raise RuntimeError("No YouTube upload to download (the search failed or found nothing).")
    src, ymeta = youtube.download_audio(url, config.CACHE_DIR / "downloads", f"download-{os.getpid()}")
    meta["youtube"] = {**meta["youtube"], **ymeta}
    meta["title"] = meta.get("title") or ymeta.get("title")
    meta["slug"] = meta.get("slug") or config.slugify(ymeta.get("title") or ymeta.get("id") or "song")
    previous = _load_meta(meta["slug"])
    if previous:
        previous_id = (previous.get("youtube") or {}).get("id")
        own_mp3 = config.AUDIO_DIR / f"{meta['slug']}.mp3"
        other_audio = previous.get("audio_file") and _resolve_saved(previous["audio_file"]) != own_mp3.resolve()
        if (previous_id and previous_id != ymeta.get("id")) or (not previous_id and other_audio):
            # A different upload or the user's own file already uses this name: never overwrite it.
            meta["slug"] = config.slugify(f"{meta['slug']}-{ymeta.get('id') or 'yt'}")
    mp3 = audio.to_mp3(src, config.AUDIO_DIR / f"{meta['slug']}.mp3")
    _store_wav(src, _wav_path(mp3))
    src.unlink(missing_ok=True)
    meta["audio_file"] = _display_path(mp3)
    meta["acquired_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _save_meta(meta)
    return meta


def chart_song(
    source: str | Path,
    *,
    meta: dict | None = None,
    overrides: dict | None = None,
    bpm: float | None = None,
    beats_per_bar: int = 4,
    subdivision: int = 4,
    shift_beats: int = 0,
    drum_stem: str | Path | None = None,
) -> dict:
    """Transcribe an audio file, or a song slug charted before, and write the chart files.

    `meta` is the full metadata of a song just fetched; `overrides` only
    replaces fields (title/artist) on top of what is already saved.
    """
    from . import chart, transcribe

    overrides = {k: v for k, v in (overrides or {}).items() if v}
    path = Path(source)
    if path.is_file():
        if meta and meta.get("slug"):
            slug = meta["slug"]
        elif overrides.get("title") or overrides.get("artist"):
            slug = config.slugify(" - ".join(x for x in (overrides.get("artist"), overrides.get("title")) if x))
        else:
            slug = config.slugify(path.stem)
        saved = _load_meta(slug) or {}
        if saved.get("audio_file") and _resolve_saved(saved["audio_file"]) != path.resolve():
            # The name belongs to other audio (e.g. the YouTube download): keep both charts.
            slug = f"{slug}-{hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:6]}"
            saved = _load_meta(slug) or {}
    else:
        slug = str(source)
        path = _audio_for_slug(slug)
        saved = _load_meta(slug) or {}
    meta = {**saved, **(meta or {}), **overrides, "slug": slug, "audio_file": _display_path(path)}

    analysis_src = Path(drum_stem) if drum_stem else path
    wav = _wav_path(analysis_src)
    if not wav.exists():
        _store_wav(analysis_src, wav)

    import soundfile as sf

    y, sr = sf.read(str(wav), dtype="float32")
    opts = transcribe.Options(
        bpm=bpm,
        beats_per_bar=beats_per_bar,
        subdivision=subdivision,
        is_drum_stem=bool(drum_stem),
        shift_beats=shift_beats,
    )
    result = transcribe.transcribe(y, sr, opts)
    result["source"] = {k: v for k, v in meta.items() if k != "warnings"}

    out = config.CHARTS_DIR / slug
    out.mkdir(parents=True, exist_ok=True)
    _save_meta(meta)
    (out / "analysis.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    chart.write_midi(result, out / "drums.mid")
    (out / "chart-draft.md").write_text(chart.markdown(result, meta), encoding="utf-8")
    return {
        "slug": slug,
        "dir": str(out),
        "files": {
            "analysis": str(out / "analysis.json"),
            "midi": str(out / "drums.mid"),
            "draft": str(out / "chart-draft.md"),
            "audio": str(path),
        },
        "bpm": result["tempo"]["bpm"],
        "bars": len(result["bars"]),
        "sections": len(result["sections"]),
        "grooves": len(result["grooves"]),
    }


def _resolve_saved(audio_file: str) -> Path:
    """An audio_file from meta.json as an absolute path (relative ones are project-relative)."""
    p = Path(audio_file)
    return (p if p.is_absolute() else config.PROJECT_DIR / p).resolve()


def _store_wav(src: Path, wav: Path) -> None:
    """Convert to the analysis WAV and drop older cached versions of the same file name."""
    audio.to_wav(src, wav)
    for old in wav.parent.glob(f"{wav.stem.rsplit('-', 1)[0]}-*.wav"):
        if old != wav and len(old.stem) == len(wav.stem):
            old.unlink(missing_ok=True)


def _audio_for_slug(slug: str) -> Path:
    """The audio behind a slug: the file recorded in its meta.json, else audio/<slug>.mp3."""
    saved = (_load_meta(slug) or {}).get("audio_file")
    candidates = [_resolve_saved(saved)] if saved else []
    candidates.append(config.AUDIO_DIR / f"{slug}.mp3")
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(f"No audio file or charted song named {slug!r} (looked in {config.AUDIO_DIR})")


def _display_path(path: Path) -> str:
    """Relative to the project when inside it (portable), absolute otherwise."""
    path = Path(path).resolve()
    try:
        return str(path.relative_to(config.PROJECT_DIR))
    except ValueError:
        return str(path)


def _wav_path(source: Path) -> Path:
    """Analysis WAV cached per source file identity (path, size, mtime), so a
    different file with the same name is never analyzed from a stale cache."""
    st = Path(source).stat()
    key = hashlib.sha1(f"{Path(source).resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:12]
    return config.CACHE_DIR / "wav" / f"{config.slugify(Path(source).stem)[:40]}-{key}.wav"


def _save_meta(meta: dict) -> None:
    out = config.CHARTS_DIR / meta["slug"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")


def _load_meta(slug: str) -> dict | None:
    p = config.CHARTS_DIR / slug / "meta.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
