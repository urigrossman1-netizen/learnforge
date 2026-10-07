# drum-agent

Ask Claude Code for a drum chart of any song. It looks the song up on Spotify,
finds the matching recording on YouTube, saves the audio as an MP3 on your
machine, transcribes the drums and writes a chart (road map, grooves, fills)
plus a MIDI file.

## Setup (once)

Requirements: [uv](https://docs.astral.sh/uv/getting-started/installation/) and
[Claude Code](https://code.claude.com/docs). Node.js is optional (used for `npx` when present).

```bash
cd drum-agent
uv run drum-agent setup     # installs everything, asks for the Spotify keys
uv run drum-agent doctor    # tests YouTube, Spotify, both MCP servers, ffmpeg, transcription
```

`setup` explains where to get the Spotify Client ID/Secret
(https://developer.spotify.com/dashboard, redirect URI `http://127.0.0.1:8888/callback`)
and stores them in `drum-agent/.env`. YouTube needs no key.

## Use

```bash
cd drum-agent
claude
> Write a drum chart for "Another One Bites the Dust" by Queen
```

Claude uses the `drum-chart` skill: Spotify MCP for metadata, YouTube MCP to pick
the upload, `drum-agent run` to download and analyze, then writes
`charts/<song>/CHART.md`.

Without Claude:

```bash
uv run drum-agent run "Queen - Another One Bites the Dust"
uv run drum-agent chart ~/Music/song.mp3 --title "Song" --artist "Band"
uv run drum-agent batch songs.example.txt
```

## What gets installed

| Piece | Source | Role |
|---|---|---|
| `@kevinwatt/yt-dlp-mcp` 0.10.0 | npm (via `npx`, or `deno` if no Node) | YouTube MCP: search, metadata, audio |
| `mcp-server-spotify` 0.3.0 | PyPI (via `uv tool run`) | Spotify MCP: search, track details |
| yt-dlp, deno | PyPI, in `.venv` | audio download + YouTube JS challenges |
| librosa, mido, imageio-ffmpeg | PyPI, in `.venv` | analysis, MIDI, ffmpeg fallback |

## Accuracy

The transcriber uses signal processing only (no model download). On the MDB
Drums research set (23 real recordings) it finds the tempo correctly on 91% of
songs. Kick and snare are reliable on isolated drum tracks and good on dense mixes;
toms, open hi-hats and ghost notes are not separated, so check fills by ear.
Pass `--drum-stem drums.wav` if you have an isolated drum track.

## Notes

- Spotify development-mode apps require the app owner to have Spotify Premium (since Feb 2026).
- Spotify is used for metadata only; its audio is DRM-protected and never downloaded.
- Audio and charts stay on your machine (`audio/`, `charts/` are git-ignored). Use them for
  your own practice and analysis.
- If YouTube asks you to sign in: `uv run drum-agent setup --cookies-from-browser chrome`.
