# Architecture

One pipeline, one chart model.

```
song name ─► identify (Spotify: details only) ─► audio (user's file, or YouTube via yt-dlp on the user's machine)
                                                    │  audio/<slug>.mp3 (never shared or committed)
                                                    ▼
  pipeline.chart_song: check audio (audio.inspect) ─► decode (ffmpeg → mono 44.1 kHz WAV, cached by file identity)
                       ─► transcribe.py (onsets per drum, tempo, beats, downbeats, bars, grooves, sections, fills)
                       ─► analysis.json + performance.mid (hits timed like the recording)
                       ─► draft.py ─► draft.drums (+ draft.html)          job.json records every stage
                                                    │
                     Claude (drum-chart skill) checks it against the recording and research, names sections,
                     adds cues and marks; never adds notes without evidence ─► chart.drums
                                                    │
  drumchart/: parser ─► model (bars, hits, sections; staff key) ─► notation (note values, beams, tuplets)
             ─► engrave (SVG systems, 4/2/1 bars per line) ─► page (HTML: road map, key, counts, colour grid,
                zoom, dark mode, print, real-drum playback, play-along with the user's recording, embedded source)
             ─► midi (General MIDI)   playability (physical checks)   edit (bar edits, history, diff)
```

## Modules

| module | role |
|---|---|
| `config.py` | toolkit dir, library (`~/DrumAgent` or `$DRUM_AGENT_HOME`), user config (`~/.config/drum-agent/.env`), tool discovery |
| `spotify.py`, `youtube.py`, `audio.py`, `pipeline.py` | find the song, get and check the audio, run the analysis, write the outputs |
| `transcribe.py` | the built-in transcriber (signal processing: mel spectral flux + NNLS drum templates, soft harmonic/percussive separation, tempogram tempo, Viterbi downbeats with restarts, grooves by clustering, sections by novelty) |
| `draft.py` | analysis → `.drums` draft (patterns, repeats, neutral section names, fills, confidence marks) |
| `performance.py` | analysis → MIDI timed like the recording |
| `drumchart/` | the chart engine (stdlib only): `parser`, `model` (instruments, meters, staff keys), `notation`, `engrave`, `page`, `render`, `midi`, `edit`, `playability`, `screenshot`; `assets/` holds the Bravura glyphs and the real drum samples |
| `gamechart.py` | Rock Band / Clone Hero chart reader (evidence for research-only charts) |
| `mcp.py`, `doctor.py`, `cli.py`, `synth.py` | MCP launcher, health check, command line, synthetic test songs |

## Decisions

- **The `.drums` text chart is the only chart model.** Pages, MIDI, PDF and PNG are all
  made from it; corrections edit it (or `drum-agent bar --set`), with history and diffs.
  The raw detected timing stays in `analysis.json` and `performance.mid`.
- **Provenance is written on every chart** (`source-kind: audio | research | generated`)
  and shown on the page; uncertain bars carry `@confidence` with the reason.
- **Notation follows the user's Drum Key picture** by default (`notation: pas` for
  Weinberg/PAS). Tests pin the positions measured from the picture.
- **Playback uses real recorded drums** (GMRockKit, three velocity layers, chokes);
  only the metronome click is synthesized.
- **Plugin packaging:** the repo root is both the marketplace and the plugin; skills
  live in `.claude/skills/` so the repo, the plugin and cloud sessions share one copy;
  `bin/drum-agent` runs the toolkit with uv from anywhere.
- **Nothing copyrighted in git:** audio, charts of commercial songs and credentials stay
  in the user's library and config folders.
