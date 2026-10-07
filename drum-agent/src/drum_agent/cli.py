"""Command line entry point: `uv run drum-agent <command>`."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from . import config

SPOTIFY_HELP = """\
Spotify credentials (for song metadata). One-time setup, about 2 minutes:
  1. Open https://developer.spotify.com/dashboard and log in with your Spotify account
     (Spotify requires the app owner to have Premium for development-mode apps).
  2. Click "Create app". Name: drum-agent. Redirect URI: http://127.0.0.1:8888/callback
     (type it exactly, then click Add). Tick "Web API". Save.
  3. Open the app -> Settings. Copy "Client ID", click "View client secret", copy it.
Paste them below (input is stored only in drum-agent/.env, which git ignores).
Press Enter to skip; YouTube search and audio still work without Spotify.
"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="drum-agent", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="store credentials and prepare tools")
    s.add_argument("--spotify-client-id")
    s.add_argument("--spotify-client-secret")
    s.add_argument(
        "--cookies-from-browser",
        help="firefox|chrome|edge|safari|brave|... (only if YouTube asks you to sign in; 'none' clears it)",
    )
    s.add_argument("--non-interactive", action="store_true")

    d = sub.add_parser("doctor", help="test YouTube, Spotify, MCP servers, ffmpeg and transcription")
    d.add_argument("--song", default=None, help='song used for the search tests, e.g. "Toto - Rosanna"')
    d.add_argument("--full", action="store_true", help="also download and chart that song end to end")
    d.add_argument("--offline", action="store_true", help="skip network checks")
    d.add_argument("--json", action="store_true")

    q = sub.add_parser("search", help="show Spotify matches and ranked YouTube candidates")
    _song_args(q)

    f = sub.add_parser("fetch", help="find a song and save its audio as audio/<slug>.mp3")
    _song_args(f)

    c = sub.add_parser("chart", help="transcribe an audio file (or a fetched slug) into a drum chart")
    c.add_argument("source", help="path to an audio file you have, or a slug from audio/")
    c.add_argument("--title")
    c.add_argument("--artist")
    c.add_argument("--json", action="store_true")
    _chart_args(c)

    r = sub.add_parser("run", help="fetch + chart in one go")
    _song_args(r)
    _chart_args(r)

    b = sub.add_parser("batch", help="run for every line of a text file ('Artist - Title' per line)")
    b.add_argument("file")
    b.add_argument("--no-spotify", action="store_true")
    b.add_argument("--json", action="store_true")
    _chart_args(b)

    m = sub.add_parser("mcp", help="start a third-party MCP server (used by .mcp.json)")
    m.add_argument("server", choices=["youtube", "spotify"])

    args = p.parse_args(argv)
    config.load_env()
    return {
        "setup": cmd_setup,
        "doctor": cmd_doctor,
        "search": cmd_search,
        "fetch": cmd_fetch,
        "chart": cmd_chart,
        "run": cmd_run,
        "batch": cmd_batch,
        "mcp": cmd_mcp,
    }[args.cmd](args)


def _song_args(p):
    p.add_argument("query", nargs="?", help='"Artist - Title" or any search text')
    p.add_argument("--title")
    p.add_argument("--artist")
    p.add_argument("--duration", type=float, help="expected length in seconds (from Spotify)")
    p.add_argument("--url", help="use this YouTube URL instead of searching")
    p.add_argument("--no-spotify", action="store_true")
    p.add_argument("--json", action="store_true")


def _chart_args(p):
    p.add_argument("--bpm", type=float, help="tempo hint if the detected tempo is half/double")
    p.add_argument("--beats-per-bar", type=int, default=4)
    p.add_argument("--subdivision", type=int, default=4, help="grid steps per beat: 4 = 16ths, 3 = triplets")
    p.add_argument("--shift-beats", type=int, default=0, help="move bar lines by N beats if beat 1 is wrong")
    p.add_argument("--drum-stem", help="isolated drum track for this song (better accuracy)")


def _emit(args, payload: dict, text: str) -> None:
    print(json.dumps(payload, indent=1) if getattr(args, "json", False) else text)


def _resolve(args, need_youtube: bool = True):
    from . import pipeline

    if not (args.query or args.title or args.artist or args.url):
        raise SystemExit("give a search query, --title/--artist, or --url")
    return pipeline.resolve(
        args.query,
        title=args.title,
        artist=args.artist,
        duration=args.duration,
        url=args.url,
        use_spotify=not args.no_spotify,
        need_youtube=need_youtube,
    )


def _describe(meta: dict) -> str:
    lines = []
    sp = meta.get("spotify")
    if sp:
        lines.append(
            f"Spotify : {sp['title']} — {', '.join(sp['artists'])} | {sp['album']} ({sp['release_date']}) "
            f"| {sp['duration_s']:.0f}s | {sp['url']}"
        )
    yt = meta.get("youtube") or {}
    if yt:
        lines.append(f"YouTube : {yt.get('title', '')} [{yt.get('channel', '')}] {yt.get('duration_s') or ''}s {yt.get('url')}")
    for alt in meta.get("youtube_alternatives", []):
        lines.append(f"   alt  : {alt['title']} [{alt['channel']}] {alt.get('duration_s')}s {alt['url']}")
    lines += [f"warning : {w}" for w in meta.get("warnings", [])]
    return "\n".join(lines)


def cmd_setup(args) -> int:
    from . import audio

    updates = {}
    env = config.os.environ
    cid, secret = args.spotify_client_id, args.spotify_client_secret
    if not (cid or secret) and not args.non_interactive and sys.stdin.isatty():
        if env.get("SPOTIFY_CLIENT_ID") and env.get("SPOTIFY_CLIENT_SECRET"):
            print("Spotify credentials already stored in drum-agent/.env "
                  "(pass --spotify-client-id/--spotify-client-secret to replace them).")
        else:
            print(SPOTIFY_HELP)
            cid = input("Spotify Client ID: ").strip()
            if cid:
                secret = getpass.getpass("Spotify Client Secret (hidden): ").strip()
    if cid:
        updates["SPOTIFY_CLIENT_ID"] = cid.strip()
    if secret:
        updates["SPOTIFY_CLIENT_SECRET"] = secret.strip()
    if args.cookies_from_browser is not None:
        value = args.cookies_from_browser.strip()
        if value.lower() in ("", "none", "off"):
            updates["DRUM_AGENT_COOKIES_FROM_BROWSER"] = ""
            env.pop("DRUM_AGENT_COOKIES_FROM_BROWSER", None)
        else:
            env["DRUM_AGENT_COOKIES_FROM_BROWSER"] = value
            try:
                config.cookies_from_browser()
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2
            updates["DRUM_AGENT_COOKIES_FROM_BROWSER"] = value
    if updates:
        config.write_env(updates)
        print(f"Saved {', '.join(updates)} to {config.ENV_FILE}")
        if "DRUM_AGENT_COOKIES_FROM_BROWSER" in updates:
            print("Restart the youtube MCP server (in Claude Code: /mcp -> youtube -> reconnect) to use it there.")
    config.load_env()
    if bool(env.get("SPOTIFY_CLIENT_ID")) != bool(env.get("SPOTIFY_CLIENT_SECRET")):
        print("warning: only one of SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET is set; Spotify needs both.",
              file=sys.stderr)
    for d in (config.AUDIO_DIR, config.CHARTS_DIR, config.CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
    _approve_project_mcp()
    print(f"ffmpeg  : {config.ffmpeg_exe()} (mp3 encoder: {'yes' if audio.has_mp3_encoder() else 'NO'})")
    print(f"yt-dlp  : {config.which('yt-dlp')}")
    print(f"deno    : {config.which('deno')}")
    print("\nNext: uv run drum-agent doctor")
    return 0


def _approve_project_mcp() -> None:
    """Pre-approve this project's .mcp.json servers for your own Claude Code (local, git-ignored)."""
    path = config.PROJECT_DIR / ".claude" / "settings.local.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    servers = json.loads((config.PROJECT_DIR / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    enabled = data.setdefault("enabledMcpjsonServers", [])
    enabled += [name for name in servers if name not in enabled]
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Claude Code: MCP servers {', '.join(enabled)} approved in {path.relative_to(config.PROJECT_DIR)}")


def cmd_doctor(args) -> int:
    from . import doctor

    checks = doctor.run(args.song or doctor.DEFAULT_SONG, network=not args.offline, full=args.full)
    return doctor.report(checks, as_json=args.json)


def cmd_search(args) -> int:
    meta = _resolve(args, need_youtube=False)
    _emit(args, meta, _describe(meta))
    return 0


def cmd_fetch(args) -> int:
    from . import pipeline

    meta = pipeline.acquire(_resolve(args))
    _emit(args, meta, _describe(meta) + f"\nSaved   : {config.PROJECT_DIR / meta['audio_file']}")
    return 0


def _chart_kwargs(args):
    return dict(
        bpm=args.bpm,
        beats_per_bar=args.beats_per_bar,
        subdivision=args.subdivision,
        shift_beats=args.shift_beats,
        drum_stem=args.drum_stem,
    )


def _chart_text(out: dict) -> str:
    return (
        f"Chart   : {out['files']['draft']}\nMIDI    : {out['files']['midi']}\n"
        f"Analysis: {out['files']['analysis']}\n"
        f"Summary : {out['bpm']} BPM, {out['bars']} bars, {out['sections']} sections, {out['grooves']} grooves"
    )


def cmd_chart(args) -> int:
    from . import pipeline

    overrides = {"title": args.title, "artist": args.artist}
    out = pipeline.chart_song(args.source, overrides=overrides, **_chart_kwargs(args))
    _emit(args, out, _chart_text(out))
    return 0


def cmd_run(args) -> int:
    from . import pipeline

    meta = pipeline.acquire(_resolve(args))
    out = pipeline.chart_song(config.PROJECT_DIR / meta["audio_file"], meta=meta, **_chart_kwargs(args))
    _emit(args, {"meta": meta, "chart": out}, _describe(meta) + "\n" + _chart_text(out))
    return 0


def cmd_batch(args) -> int:
    from . import pipeline

    raw = Path(args.file).read_bytes()
    # Windows PowerShell 5 writes UTF-16 with `>`; Notepad may add a UTF-8 BOM.
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig")
    songs = [
        line.strip().lstrip("\ufeff")
        for line in text.splitlines()
        if line.strip() and not line.strip().lstrip("\ufeff").startswith("#")
    ]
    results, failed = [], 0
    for i, song in enumerate(songs, 1):
        print(f"[{i}/{len(songs)}] {song}", file=sys.stderr)
        try:
            meta = pipeline.resolve(song, use_spotify=not args.no_spotify)
            meta = pipeline.acquire(meta)
            out = pipeline.chart_song(config.PROJECT_DIR / meta["audio_file"], meta=meta, **_chart_kwargs(args))
            results.append({"song": song, "ok": True, "chart": out, "warnings": meta.get("warnings", [])})
            for w in meta.get("warnings", []):
                if not w.startswith("Spotify credentials not set"):
                    print(f"   warning: {w}", file=sys.stderr)
            print(f"   -> {out['files']['draft']}", file=sys.stderr)
        except Exception as e:
            failed += 1
            results.append({"song": song, "ok": False, "error": str(e)})
            print(f"   !! {e}", file=sys.stderr)
    _emit(args, {"results": results}, f"{len(songs) - failed}/{len(songs)} songs charted")
    return 1 if failed else 0


def cmd_mcp(args) -> int:
    from . import mcp

    return mcp.launch(args.server)


if __name__ == "__main__":
    sys.exit(main())
