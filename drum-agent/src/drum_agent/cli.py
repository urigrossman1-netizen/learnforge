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
Paste them below (stored only in your user config folder, never in a repository).
Press Enter to skip; YouTube search and audio still work without Spotify.
"""


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["game-chart"]:  # its own options, help included
        from . import gamechart

        return gamechart.main(argv[1:]) or 0
    p = argparse.ArgumentParser(prog="drum-agent", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="store credentials and prepare tools")
    s.add_argument("--spotify-client-id")
    s.add_argument("--spotify-client-secret")
    s.add_argument(
        "--cookies-from-browser",
        help="firefox|chrome|edge|safari|brave|... (only if YouTube asks you to sign in; 'none' clears it)",
    )
    s.add_argument("--screenshots", action="store_true",
                   help="also install Playwright + Chromium for PNG/PDF export (about 200 MB)")
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

    c = sub.add_parser("analyze", aliases=["chart"],
                       help="listen to an audio file (or a fetched slug) and write a draft chart")
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

    rn = sub.add_parser("render", help="engrave a .drums chart into a zoomable HTML page (and PNG/PDF)")
    rn.add_argument("chart", help="path to a .drums file")
    rn.add_argument("-o", "--out", help="HTML file to write (default: next to the chart)")
    rn.add_argument("--artifact", action="store_true", help="body-only HTML for publishing as a claude.ai Artifact")
    rn.add_argument("--png", help="also save a screenshot (needs Playwright Chromium)")
    rn.add_argument("--pdf", help="also save a print-ready PDF (needs Playwright Chromium)")
    rn.add_argument("--midi", help="also save the chart as a General MIDI file")
    rn.add_argument("--paper", default="letter", choices=["letter", "a4"])
    rn.add_argument("--width", type=int, default=1300, help="screenshot viewport width in px")

    ck = sub.add_parser("check", help="validate a .drums chart and print its form and timing summary")
    ck.add_argument("chart", help="path to a .drums file")

    br = sub.add_parser("bar", help="show one bar of a chart, or replace it (--set) without touching other bars")
    br.add_argument("chart")
    br.add_argument("number", type=int)
    br.add_argument("--set", dest="rows", help='new rows, e.g. "HH x-x- x-x- x-x- x-o-; SN ---- x--- ---- x---"')

    hi = sub.add_parser("history", help="list the saved versions of a chart (kept on every edit and render)")
    hi.add_argument("chart")
    for name, helptext in (("undo", "go back to the previous version of a chart"),
                           ("redo", "go forward again after undo")):
        u = sub.add_parser(name, help=helptext)
        u.add_argument("chart")
    rs = sub.add_parser("restore", help="put saved version N of a chart back (see history)")
    rs.add_argument("chart")
    rs.add_argument("version", type=int)

    df = sub.add_parser("diff", help="list what changed between two charts, bar by bar (e.g. draft vs final)")
    df.add_argument("old")
    df.add_argument("new")

    ex = sub.add_parser("extract", help="recover the .drums source from a rendered chart page")
    ex.add_argument("page", help="a chart .html page made by drum-agent render")
    ex.add_argument("-o", "--out", help=".drums file to write (default: print it)")

    gc = sub.add_parser("game-chart", add_help=False,
                        help="read a Rock Band / Clone Hero drum chart (form, tempo map, lanes per bar) as evidence")
    gc.add_argument("rest", nargs=argparse.REMAINDER)

    m = sub.add_parser("mcp", help="start a third-party MCP server (used by .mcp.json)")
    m.add_argument("server", choices=["youtube", "spotify"])

    args = p.parse_args(argv)
    config.load_env()
    try:
        return _dispatch(args)
    except KeyboardInterrupt:
        print("stopped.", file=sys.stderr)
        return 130
    except Exception as e:  # one clear line for the user; DRUM_AGENT_DEBUG=1 shows the traceback
        if config.os.environ.get("DRUM_AGENT_DEBUG"):
            raise
        print(f"error: {e}", file=sys.stderr)
        if not isinstance(e, (ValueError, FileNotFoundError)):
            print("       (run `drum-agent doctor` to check the setup; DRUM_AGENT_DEBUG=1 for details)", file=sys.stderr)
        return 2


def _dispatch(args) -> int:
    return {
        "setup": cmd_setup,
        "doctor": cmd_doctor,
        "search": cmd_search,
        "fetch": cmd_fetch,
        "analyze": cmd_chart,
        "chart": cmd_chart,
        "run": cmd_run,
        "batch": cmd_batch,
        "render": cmd_render,
        "check": cmd_check,
        "extract": cmd_extract,
        "bar": cmd_bar,
        "history": cmd_history,
        "undo": cmd_undo,
        "redo": cmd_undo,
        "restore": cmd_undo,
        "diff": cmd_diff,
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
            print(f"Spotify credentials already stored in {config.ENV_FILE} "
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
                parsed = config.cookies_from_browser()
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2
            if parsed and parsed[2]:
                print("note: the YouTube MCP server ignores the +KEYRING part; drum-agent's own downloads use it.")
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
    if args.screenshots and _install_screenshots() != 0:
        return 1
    print(f"ffmpeg  : {config.ffmpeg_exe()} (mp3 encoder: {'yes' if audio.has_mp3_encoder() else 'NO'})")
    print(f"yt-dlp  : {config.which('yt-dlp')}")
    print(f"deno    : {config.which('deno')}")
    print("\nNext: uv run drum-agent doctor")
    return 0


def _install_screenshots() -> int:
    """Playwright into this environment, then its Chromium (for render --png/--pdf)."""
    import shutil
    import subprocess

    uv = shutil.which("uv")
    if not uv:
        print("Installing screenshot support needs uv on PATH.", file=sys.stderr)
        return 1
    steps = [
        [uv, "sync", "--project", str(config.TOOLKIT_DIR), "--frozen", "--inexact", "--group", "screenshots"],
        [sys.executable, "-m", "playwright", "install", "chromium"],
    ]
    for i, cmd in enumerate(steps):
        print("$ " + " ".join(cmd[1:] if cmd[0] == uv else ["playwright", "install", "chromium"]))
        if subprocess.run(cmd).returncode != 0:
            from .drumchart import screenshot

            if i == 1 and screenshot._exe():
                print(f"Using the Chromium already installed at {screenshot._exe()}.")
                break
            print("Screenshot support could not be installed (see above).", file=sys.stderr)
            return 1
    print("Screenshots: ready (drum-agent render chart.drums --png chart.png --pdf chart.pdf)")
    return 0


def _approve_project_mcp() -> None:
    """Pre-approve this project's .mcp.json servers for your own Claude Code (local, git-ignored)."""
    path = config.TOOLKIT_DIR / ".claude" / "settings.local.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    servers = json.loads((config.TOOLKIT_DIR / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    enabled = data.setdefault("enabledMcpjsonServers", [])
    enabled += [name for name in servers if name not in enabled]
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Claude Code: MCP servers {', '.join(enabled)} approved in {path}")


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
        f"Draft   : {out['files']['draft']}\nPage    : {out['files']['page']}\n"
        f"MIDI    : {out['files']['midi']} (timed like the recording)\nAnalysis: {out['files']['analysis']}\n"
        f"Summary : {out['bpm']} BPM, {out['time']}, {out['bars']} bars, {out['sections']} sections, "
        f"{out['grooves']} grooves"
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

    text = config.read_text_any(Path(args.file))
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
            print(f"   -> {out['files']['page']}", file=sys.stderr)
        except Exception as e:
            failed += 1
            results.append({"song": song, "ok": False, "error": str(e)})
            print(f"   !! {e}", file=sys.stderr)
    _emit(args, {"results": results}, f"{len(songs) - failed}/{len(songs)} songs charted")
    return 1 if failed else 0


def _load_chart(path: str):
    from .drumchart import render

    try:
        chart = render.load(path)
    except render.ChartError as e:
        print(f"ERROR {path}: {e}", file=sys.stderr)
        return None
    except OSError as e:
        print(f"ERROR {path}: {e.strerror or e}", file=sys.stderr)
        return None
    for w in chart.warnings:
        print("warning:", w, file=sys.stderr)
    print(render.summary(chart))
    return chart


def cmd_check(args) -> int:
    return 0 if _load_chart(args.chart) else 2


def cmd_render(args) -> int:
    from .drumchart import render

    chart = _load_chart(args.chart)
    if chart is None:
        return 2
    from .drumchart import edit

    source = Path(args.chart).read_text(encoding="utf-8")
    edit.snapshot(args.chart, source)
    html = render.render_html(chart, standalone=not args.artifact, source=source)
    out = Path(args.out) if args.out else Path(args.chart).with_suffix(".html")
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html) // 1024} KB)")
    if args.midi:
        from .drumchart import midi

        print(f"wrote {midi.write_midi(chart, args.midi)}")
    if args.png or args.pdf:
        from .drumchart import screenshot

        try:
            if args.png:
                screenshot.screenshot(str(out), args.png, width=args.width)
                print(f"wrote {args.png}")
            if args.pdf:
                screenshot.pdf(str(out), args.pdf, paper=args.paper)
                print(f"wrote {args.pdf}")
        except ImportError:
            print("PNG/PDF need Playwright: run `drum-agent setup --screenshots` once.", file=sys.stderr)
            return 3
    return 0


def cmd_bar(args) -> int:
    from .drumchart import edit, render

    path = Path(args.chart)
    text = path.read_text(encoding="utf-8")
    try:
        if not args.rows:
            print(edit.show_bar(text, args.number))
            return 0
        new = edit.set_bar(text, args.number, args.rows)
    except (ValueError, render.ChartError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    edit.snapshot(path, text)
    path.write_text(new, encoding="utf-8")
    edit.snapshot(path, new)
    print("\n".join(edit.diff(text, new)) or "no change")
    print(edit.show_bar(new, args.number))
    return 0


def cmd_history(args) -> int:
    from .drumchart import edit

    vs = edit.versions(args.chart)
    if not vs:
        print(f"{args.chart} has no saved versions yet (they are kept on every bar edit and render).")
        return 0
    current = Path(args.chart).read_text(encoding="utf-8") if Path(args.chart).exists() else ""
    here = edit._position(Path(args.chart), current)
    for i, v in enumerate(vs, 1):
        stamp = f"{v.name[:4]}-{v.name[4:6]}-{v.name[6:8]} {v.name[9:11]}:{v.name[11:13]}:{v.name[13:15]}"
        print(f"{i:>3}  {stamp}{'   <- current' if here == i - 1 else ''}")
    return 0


def cmd_undo(args) -> int:
    from .drumchart import edit

    try:
        if args.cmd == "restore":
            chosen = edit.restore(args.chart, args.version)
        else:
            chosen = getattr(edit, args.cmd)(args.chart)
    except (ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(f"{args.chart} now holds saved version {edit.versions(args.chart).index(chosen) + 1}; "
          "re-render it to update the page.")
    return 0


def cmd_diff(args) -> int:
    from .drumchart import edit, render

    try:
        changes = edit.diff(Path(args.old).read_text(encoding="utf-8"), Path(args.new).read_text(encoding="utf-8"))
    except (OSError, render.ChartError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print("\n".join(changes) if changes else "no musical difference")
    return 0


def cmd_extract(args) -> int:
    from .drumchart import render

    source = render.extract(Path(args.page).read_text(encoding="utf-8", errors="replace"))
    if source is None:
        print(f"{args.page} has no embedded chart source (it was rendered before sources were embedded).",
              file=sys.stderr)
        return 2
    if args.out:
        Path(args.out).write_text(source, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(source)
    return 0


def cmd_mcp(args) -> int:
    from . import mcp

    return mcp.launch(args.server)


if __name__ == "__main__":
    sys.exit(main())
