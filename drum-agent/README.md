# drum-agent

Ask Claude Code for a drum chart of any song. It looks the song up on Spotify,
finds the matching recording on YouTube, saves the audio as an MP3 on your
machine, transcribes the drums and writes a chart (road map, grooves, fills)
plus a MIDI file.

## Setup (once)

Requirements: [uv](https://docs.astral.sh/uv/getting-started/installation/) and
[Claude Code](https://code.claude.com/docs). Nothing else: uv fetches Python 3.13,
yt-dlp, deno and a bundled ffmpeg; Node.js 18+ is used for `npx` if present, deno otherwise.

```bash
cd drum-agent
uv run drum-agent setup     # installs everything, asks for the Spotify keys, approves the MCP servers
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
`charts/<song>/CHART.md`. The first Spotify MCP search opens a one-time login in
your browser.

Without Claude:

```bash
uv run drum-agent run "Queen - Another One Bites the Dust"
uv run drum-agent chart ~/Music/song.mp3 --title "Song" --artist "Band"
uv run drum-agent chart <slug> --bpm 110      # re-analyze without downloading again
uv run drum-agent batch songs.example.txt
```

## What gets installed

| Piece | Source | Role |
|---|---|---|
| `@kevinwatt/yt-dlp-mcp` 0.10.0 | npm (via `npx`, or `deno` without Node) | YouTube MCP: search, metadata, audio |
| `mcp-server-spotify` 0.3.0 | PyPI (via `uv tool run`, MCP SDK < 2) | Spotify MCP: search, track details |
| yt-dlp, deno | PyPI, in `.venv` | audio download + YouTube JS challenges |
| librosa, mido, imageio-ffmpeg | PyPI, in `.venv` | analysis, MIDI, ffmpeg fallback |

## Accuracy

The transcriber uses signal processing only (no model download). Measured on
[MDB Drums](https://github.com/CarlSouthall/MDBDrums), 23 real recordings with
hand-annotated hits (`uv run python eval/mdb_drums.py` reproduces it):

| | Kick F1 | Snare F1 | Hi-hat F1 | Tempo right | Bar 1 right |
|---|---|---|---|---|---|
| Rock/pop/funk/metal (15 songs), full mix | 0.95 | 0.77 | 0.66 | 93% | 93% |
| Same songs, isolated drum stems | 0.97 | 0.85 | 0.85 | 93% | 93% |
| All 23 incl. jazz, full mix | 0.78 | 0.67 | 0.60 | 91% | 76% |

The detection thresholds were tuned on this same set, so expect somewhat lower
scores on other music. Jazz, brushes and ride-led or swung grooves are much less
accurate. Toms are not separated (fills show them as snare or kick), rides appear
on the hi-hat row, and open hats and ghost notes are often missed. Check fills
by ear, and pass `--drum-stem drums.wav` if you have an isolated drum track.

## Notes

- Spotify development-mode apps require the app owner to have Spotify Premium (since Feb 2026).
- Spotify is used for metadata only; its audio is DRM-protected and never downloaded.
- Audio and charts stay on your machine (`audio/`, `charts/` are git-ignored). Use them for
  your own practice and analysis.
- If YouTube asks you to sign in ("confirm you're not a bot"): log in to YouTube in Firefox and
  run `uv run drum-agent setup --cookies-from-browser firefox`, then reconnect the youtube MCP
  server in Claude Code (`/mcp`). On Windows, Chrome/Edge cookies only work with the browser
  closed. `--cookies-from-browser none` turns it off again.
- Credentials: Spotify app keys in `drum-agent/.env`; the Spotify MCP login in
  `~/.spotify-mcp/credentials.json`. To revoke that login, delete the file and remove the app
  at https://www.spotify.com/account/apps/.
