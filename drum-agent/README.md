# drum-agent

Ask Claude for the drums of any song. The drum agent finds the song, gets the
audio (your own file, or YouTube on your computer), listens for the drums, and
writes a chart you can actually read:

- an engraved drum staff in **your Drum Key notation**, with the count
  (`1 e & a`) and a colour hit grid under every bar;
- a road map of the song, repeat signs, fills, dynamics and cues;
- **zoom** that reflows the chart (4 → 2 → 1 bars per line), dark mode, print to PDF;
- **playback with real recorded drums**, slow-down, loop a section, click, count-in;
- MIDI of the chart and MIDI of the performance timed like the recording;
- honest marks on every bar the analysis is unsure about.

It works as a Claude Code plugin, so every project you open has it.

## Use it in any project

**Claude Code on your computer** (terminal or desktop app). You need
[uv](https://docs.astral.sh/uv/getting-started/installation/). In Claude Code:

```
/plugin install drum-agent --marketplace urigrossman1-netizen/drum-agent
```

(on older Claude Code: `/plugin marketplace add urigrossman1-netizen/drum-agent`,
then `/plugin install drum-agent@drum-agent-tools`). Then ask Claude to
**set up the drum agent**: it installs what is missing and runs a health check.
Spotify keys are optional (they add exact song details; YouTube needs no key):
to add them, run the `drum-agent setup` command Claude shows you in a terminal
and paste the two keys when it asks. Then ask:

```
Write a drum chart for "Another One Bites the Dust" by Queen
Chart the drums of ~/Music/our-demo.wav
Make the chorus fill in chart.drums a 16th-note tom run and re-render it
```

**Claude Code in the cloud** (claude.ai/code or a cloud session in the app):
add the `drum-agent` repository in the repo picker next to your project. The
skill loads from it. Cloud sessions cannot reach YouTube or Spotify, so upload
the song file (or put it in Google Drive) and ask for its chart.

**Inside this repository**: `uv run drum-agent ...` works directly; songs and
charts go to `audio/` and `charts/` here (git-ignored).

## Commands

| command | what it does |
|---|---|
| `drum-agent run "Artist - Title"` | find the song, save the audio, write `draft.drums` + `draft.html` |
| `drum-agent analyze song.mp3` | the same for a file you have (`--bpm`, `--beats-per-bar`, `--subdivision`, `--shift-beats`, `--drum-stem`) |
| `drum-agent render chart.drums` | engrave a chart page (`--midi`, `--pdf`, `--png`, `--artifact`) |
| `drum-agent check chart.drums` | validate a chart; print its form and timing against the recording |
| `drum-agent extract chart.html` | recover the editable chart from any chart page |
| `drum-agent game-chart notes.mid` | read a Rock Band / Clone Hero chart (form, tempo map, lanes) as evidence |
| `drum-agent search` / `fetch` / `batch` | look up, download, or run a list of songs |
| `drum-agent setup` / `doctor` | credentials and health check |

Charts are plain text (`.drums`), written like a lead sheet; see
[`.claude/skills/drum-chart/references/format.md`](.claude/skills/drum-chart/references/format.md).
[`examples/drum-key.drums`](examples/drum-key.drums) shows every instrument
and technique of the Drum Key.

## How well it listens

The built-in transcriber is signal processing (no model download). Measured on
[MDB Drums](https://github.com/CarlSouthall/MDBDrums), 23 real recordings with
hand-annotated hits (`uv run python eval/mdb_drums.py`):

| | Kick F1 | Snare F1 | Hi-hat F1 | Tempo right | Bar 1 right |
|---|---|---|---|---|---|
| Rock/pop/funk/metal (15 songs), full mix | 0.95 | 0.77 | 0.66 | 93% | 93% |
| Same songs, isolated drum stems | 0.97 | 0.85 | 0.84 | 93% | 93% |
| All 23 incl. jazz, full mix | 0.78 | 0.67 | 0.60 | 91% | 76% |

It does not yet separate toms (fills show them as snare or kick), puts the ride
on the hi-hat row, and misses most open hi-hats and ghost notes, so Claude marks
those bars and checks fills against research. Every chart says how it was made.

## Your data

- Songs and charts: `~/DrumAgent` (or `$DRUM_AGENT_HOME`). Audio is for your own
  practice and analysis: it is never uploaded, published or committed.
- Keys: `~/.config/drum-agent/.env` (Spotify app keys, from `drum-agent setup`)
  and `~/.spotify-mcp/credentials.json` (the Spotify MCP login). Spotify is used
  for song details only; its audio is DRM-protected.
- If YouTube asks you to sign in ("confirm you're not a bot"), log in to YouTube in
  Firefox and run `drum-agent setup --cookies-from-browser firefox`.

## Credits

- Music symbols: [Bravura](https://github.com/steinbergmedia/bravura) © Steinberg, SIL Open Font License 1.1.
- Drum sounds: [Hydrogen GMRockKit](https://github.com/hydrogen-music/hydrogen/tree/master/data/drumkits/GMRockKit)
  by Glen MacArthur and Sebastian Moors, GPL-3.0 (see `src/drum_agent/drumchart/assets/kit/NOTICE.md`).
- MCP servers: [`@kevinwatt/yt-dlp-mcp`](https://github.com/kevinwatt/yt-dlp-mcp) and
  [`mcp-server-spotify`](https://pypi.org/project/mcp-server-spotify/).
- Evaluation data: MDB Drums (CC BY-NC-SA 4.0), used for measurement only, not included.
