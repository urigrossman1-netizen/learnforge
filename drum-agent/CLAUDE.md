# drum-agent

Finds a song, gets its audio locally, and writes a drum chart for it.

## Layout

- `.mcp.json`: two maintained third-party MCP servers, started through `uv run drum-agent mcp <name>`
  (that launcher only adds the project's yt-dlp/deno/ffmpeg to PATH and the Spotify keys from `.env`):
  - `youtube`: [`@kevinwatt/yt-dlp-mcp`](https://github.com/kevinwatt/yt-dlp-mcp), keyless YouTube search, metadata, audio.
  - `spotify`: [`mcp-server-spotify`](https://pypi.org/project/mcp-server-spotify/), Spotify Web API (Feb 2026 rules).
- `src/drum_agent/`: the local pipeline, independent of the MCP servers.
  - `spotify.py` (client-credentials search) and `youtube.py` (yt-dlp search/download)
  - `audio.py` (ffmpeg: MP3 to keep, mono WAV to analyze), `transcribe.py` (drum transcription),
    `chart.py` (Markdown draft + MIDI), `pipeline.py` (glue), `doctor.py` (connectivity test)
- Outputs (git-ignored): `audio/<slug>.mp3`, `charts/<slug>/{analysis.json,chart-draft.md,drums.mid,CHART.md}`.

## Commands

```bash
uv run drum-agent doctor                       # test everything (add --full to chart a real song)
uv run drum-agent run "Artist - Title" --json  # search + download + chart
uv run drum-agent chart <file-or-slug>         # chart audio you already have
uv run drum-agent batch songs.txt              # many songs
uv run --group dev pytest                      # tests (synthetic audio, no network)
uv run python eval/mdb_drums.py                # accuracy on 23 annotated real recordings
```

## Rules

- For a drum chart request, follow the `drum-chart` skill.
- Spotify is for metadata only; never try to download Spotify audio (DRM).
- Downloaded audio is for the user's personal analysis. Keep it in `audio/`; never commit it.
- Credentials live in `.env` (Spotify app keys, written by `uv run drum-agent setup`) and in
  `~/.spotify-mcp/credentials.json` (the Spotify MCP's login tokens). Never read, print or commit either.
