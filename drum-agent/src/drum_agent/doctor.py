"""`drum-agent doctor`: end-to-end connectivity and pipeline test."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from . import audio, config, mcp, spotify, youtube

# yt-dlp's own 10-second test upload: tiny, and published for exactly this purpose.
TEST_VIDEO = "https://www.youtube.com/watch?v=BaW_jenozKc"
DEFAULT_SONG = "Queen - Another One Bites the Dust"


@dataclass
class Check:
    name: str
    status: str  # PASS | FAIL | MISSING | SKIP
    detail: str
    fix: str = ""
    seconds: float = 0.0


def _run(name, fn, checks):
    t0 = time.time()
    try:
        status, detail, fix = fn()
    except Exception as e:  # report every failure, keep testing the rest
        status, detail, fix = "FAIL", f"{type(e).__name__}: {e}", _hint(e)
    detail = " ".join(detail.split("; please report this issue")[0].split())[:300]
    checks.append(Check(name, status, detail, fix, round(time.time() - t0, 1)))
    return checks[-1]


def _hint(e: Exception) -> str:
    text = str(e)
    if "403" in text and ("Tunnel" in text or "proxy" in text.lower()):
        return "This network blocks the host (proxy 403). Allow youtube.com/googlevideo.com/spotify.com or run locally."
    if "Sign in to confirm" in text or "not a bot" in text:
        return ("YouTube wants a signed-in session: `uv run drum-agent setup --cookies-from-browser firefox` "
                "(log in to YouTube in that browser first; on Windows Chrome/Edge must be closed).")
    if "DRUM_AGENT_COOKIES_FROM_BROWSER" in text:
        return "Fix or clear it: `uv run drum-agent setup --cookies-from-browser firefox` (or `none`)."
    if "npx" in text or "No such file" in text:
        return "Run `uv sync` in drum-agent/ (installs deno, which runs the YouTube MCP without Node.js)."
    return ""


def run(song: str = DEFAULT_SONG, network: bool = True, full: bool = False) -> list[Check]:
    config.load_env()
    checks: list[Check] = []
    work = config.CACHE_DIR / "doctor"
    work.mkdir(parents=True, exist_ok=True)

    _run("ffmpeg", _ffmpeg, checks)
    _run("yt-dlp + JS runtime", _ytdlp, checks)
    if network:
        _run("YouTube search (yt-dlp)", lambda: _youtube_search(song), checks)
        _run("Spotify search (Web API)", lambda: _spotify_search(song), checks)
        _run("YouTube MCP server", lambda: _youtube_mcp(song), checks)
        _run("Spotify MCP server", lambda: _spotify_mcp(song), checks)
        acq = _run("YouTube audio acquisition", lambda: _acquire(work), checks)
    else:
        for n in ("YouTube search (yt-dlp)", "Spotify search (Web API)", "YouTube MCP server",
                  "Spotify MCP server", "YouTube audio acquisition"):
            checks.append(Check(n, "SKIP", "--offline"))
        acq = checks[-1]
    _run("Audio file creation (MP3 + WAV)", lambda: _audio_files(work, acq.status == "PASS"), checks)
    _run("Drum transcription pipeline", lambda: _transcription(work), checks)
    if full and network:
        _run(f"Full song: {song}", lambda: _full_song(song), checks)
    return checks


def _ffmpeg():
    exe = config.ffmpeg_exe()
    out = subprocess.run([exe, "-version"], capture_output=True, text=True).stdout.splitlines()
    if not audio.has_mp3_encoder():
        return "FAIL", f"{exe}: no libmp3lame encoder", "Install a full ffmpeg build."
    source = "system" if exe != _bundled() else "bundled (imageio-ffmpeg)"
    return "PASS", f"{out[0] if out else exe} [{source}], MP3 encoder OK", ""


def _bundled():
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def _ytdlp():
    import yt_dlp

    deno = config.which("deno")
    if not deno:
        return "FAIL", f"yt-dlp {yt_dlp.version.__version__}, no deno", "Run `uv sync` in drum-agent/."
    ver = subprocess.run([deno, "--version"], capture_output=True, text=True).stdout.split("\n")[0]
    return "PASS", f"yt-dlp {yt_dlp.version.__version__}; {ver}", ""


def _youtube_search(song):
    results = youtube.rank(youtube.search(song, 5), query=song)
    if not results:
        return "FAIL", "no results", ""
    top = results[0]
    return "PASS", f"{len(results)} results; top: {top['title']!r} [{top['channel']}] {top['url']}", ""


def _spotify_search(song):
    if not spotify.has_credentials():
        return "MISSING", "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET not set", "Run `uv run drum-agent setup` and paste them."
    tracks = spotify.search_tracks(song, limit=3)
    if not tracks:
        return "FAIL", "no tracks returned", ""
    t = tracks[0]
    mins = f"{int(t['duration_s'] // 60)}:{int(t['duration_s'] % 60):02d}"
    return "PASS", f"{t['title']} — {', '.join(t['artists'])} ({t['album']}, {t['release_date']}, {mins}) {t['url']}", ""


def _mcp_text(result) -> str:
    return "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")


def _youtube_mcp(song):
    cmd, cwd = mcp.project_server("youtube")
    with mcp.StdioClient(cmd, cwd) as client:
        info = client.initialize()
        tools = {t["name"] for t in client.request("tools/list")["tools"]}
        needed = {"ytdlp_search_videos", "ytdlp_download_audio", "ytdlp_get_video_metadata_summary"}
        if not needed <= tools:
            return "FAIL", f"missing tools: {sorted(needed - tools)}", ""
        res = client.request(
            "tools/call",
            {"name": "ytdlp_search_videos", "arguments": {"query": song, "maxResults": 3, "response_format": "json"}},
            timeout=90,
        )
        text = _mcp_text(res)
        if res.get("isError"):
            return "FAIL", f"{len(tools)} tools listed, search failed: {text[:300]}", _hint(RuntimeError(text))
        try:
            videos = json.loads(text).get("videos", [])
        except json.JSONDecodeError:
            videos = []
        top = f"top: {videos[0]['title']!r}" if videos else text[:120]
        name = info.get("serverInfo", {}).get("name", "yt-dlp-mcp")
        return "PASS", f"{name}: {len(tools)} tools; search OK, {top}", ""


def _spotify_mcp(song):
    if not spotify.has_credentials():
        return "MISSING", "needs the same Spotify Client ID/Secret", "Run `uv run drum-agent setup`."
    cmd, cwd = mcp.project_server("spotify")
    with mcp.StdioClient(cmd, cwd) as client:
        info = client.initialize()
        tools = {t["name"] for t in client.request("tools/list")["tools"]}
        if "search" not in tools:
            return "FAIL", f"no search tool in {sorted(tools)[:8]}", ""
        name = info.get("serverInfo", {}).get("name", "spotify")
        token = Path.home() / ".spotify-mcp" / "credentials.json"
        if not token.exists():
            return "SKIP", (
                f"{name}: starts and lists {len(tools)} tools; your Spotify login is not done yet"
            ), (
                "In Claude Code ask for any Spotify search once: a browser tab asks you to log in "
                "(redirect URI http://127.0.0.1:8888/callback must be in your Spotify app). Then re-run doctor."
            )
        res = client.request(
            "tools/call", {"name": "search", "arguments": {"query": song, "types": "track", "limit": 3}}, timeout=60
        )
        if res.get("isError"):
            return "FAIL", _mcp_text(res)[:300], ""
        return "PASS", f"{name}: {len(tools)} tools; search OK: {_mcp_text(res)[:120]!r}", ""


def _acquire(work):
    for old in work.glob("acquired.*"):
        old.unlink()
    path, meta = youtube.download_audio(TEST_VIDEO, work, "acquired")
    size = path.stat().st_size
    if size < 10_000:
        return "FAIL", f"{path.name} only {size} bytes", ""
    return "PASS", f"{meta['title']!r} -> {path.name} ({size // 1024} KiB, {meta.get('acodec')})", ""


def _audio_files(work, have_download):
    import soundfile as sf

    if have_download:
        src = next(work.glob("acquired.*"))
        origin = "downloaded audio"
    else:
        from . import synth

        y, sr, _ = synth.make_song()
        src = work / "synthetic.wav"
        sf.write(str(src), y[: sr * 8], sr)
        origin = "synthetic audio (download unavailable)"
    mp3 = audio.to_mp3(src, work / "test.mp3")
    wav = audio.to_wav(src, work / "test.wav")
    d_mp3, d_wav = audio.duration(mp3), audio.duration(wav)
    if d_wav < 0.5 or abs(d_mp3 - d_wav) > 1.0:
        return "FAIL", f"durations mp3={d_mp3:.2f}s wav={d_wav:.2f}s", ""
    return "PASS", f"from {origin}: test.mp3 ({mp3.stat().st_size // 1024} KiB, {d_mp3:.1f}s), test.wav (mono 44.1 kHz)", ""


def _transcription(work):
    """Round-trip a synthetic song with known drums through MP3 and transcribe it."""
    import soundfile as sf

    from . import synth, transcribe

    y, sr, truth = synth.make_song()
    src = work / "groove.wav"
    sf.write(str(src), y, sr)
    mp3 = audio.to_mp3(src, work / "groove.mp3")
    wav = audio.to_wav(mp3, work / "groove-decoded.wav")
    y2, sr2 = sf.read(str(wav), dtype="float32")
    result = transcribe.transcribe(y2, sr2)
    scores = synth.score(truth["hits"], transcribe.hit_times(result))
    bpm_err = abs(result["tempo"]["bpm"] - truth["bpm"]) / truth["bpm"]
    downbeat_err = abs(result["tempo"]["first_downbeat_s"] - truth["first_downbeat_s"])
    f1 = {d: scores[d]["f1"] for d in ("kick", "snare", "hihat")}
    ok = f1["kick"] >= 0.9 and f1["snare"] >= 0.9 and f1["hihat"] >= 0.8 and bpm_err < 0.02 and downbeat_err < 0.06
    detail = (
        f"F1 kick {f1['kick']:.2f} snare {f1['snare']:.2f} hi-hat {f1['hihat']:.2f}; "
        f"tempo {result['tempo']['bpm']} vs {truth['bpm']} BPM; bar 1 at {result['tempo']['first_downbeat_s']}s "
        f"(truth {truth['first_downbeat_s']}s); {len(result['sections'])} sections"
    )
    return ("PASS" if ok else "FAIL"), detail, ""


def _full_song(song):
    from . import pipeline

    meta = pipeline.resolve(song)
    meta = pipeline.acquire(meta)
    out = pipeline.chart_song(config.PROJECT_DIR / meta["audio_file"], meta=meta)
    warn = f" Warnings: {'; '.join(meta['warnings'])}" if meta.get("warnings") else ""
    return "PASS", f"{meta['audio_file']} -> {out['dir']} ({out['bpm']} BPM, {out['bars']} bars).{warn}", ""


def report(checks: list[Check], as_json: bool = False) -> int:
    if as_json:
        print(json.dumps([asdict(c) for c in checks], indent=1))
    else:
        width = max(len(c.name) for c in checks)
        for c in checks:
            print(f"{c.status:<7} {c.name:<{width}}  {c.detail}  ({c.seconds}s)")
            if c.fix and c.status != "PASS":
                print(f"{'':<7} {'':<{width}}  -> {c.fix}")
        bad = [c for c in checks if c.status in ("FAIL", "MISSING")]
        print()
        print("ALL CHECKS PASSED" if not bad else f"{len(bad)} check(s) need attention: " + ", ".join(c.name for c in bad))
    return 1 if any(c.status in ("FAIL", "MISSING") for c in checks) else 0
