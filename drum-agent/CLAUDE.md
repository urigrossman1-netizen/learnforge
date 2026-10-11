# drum-agent

Listens to a song and writes its drum chart. This repo is both a Python project
(`src/drum_agent`, CLI `drum-agent`) and a Claude Code plugin (`.claude-plugin/`,
skills in `.claude/skills/`, launcher in `bin/`, MCP servers in `.mcp.json`).

## Pipeline (one chart model)

audio (user file, or YouTube via yt-dlp on the user's machine) → `transcribe.py`
(drum hits, tempo, bars, grooves, sections, fills) → `analysis.json` →
`draft.py` → `draft.drums` → Claude/user review → `chart.drums` →
`drumchart/` (parse, engrave, page with zoom and real-drum playback, MIDI).
The `.drums` text chart is the only chart model; every export comes from it.
`performance.py` writes the detected hits as MIDI timed like the recording.

## Layout

- `src/drum_agent/`
  - acquisition: `spotify.py` (metadata only), `youtube.py`, `audio.py` (ffmpeg), `pipeline.py`
  - listening: `transcribe.py`, `synth.py` (synthetic test songs)
  - charts: `draft.py`, `performance.py`, `drumchart/` (`parser`, `model` incl. staff keys,
    `notation`, `engrave`, `page`, `midi`, `render`, `screenshot`, `assets/` Bravura glyphs + real drum samples)
  - `gamechart.py` (Rock Band / Clone Hero reader), `mcp.py`, `doctor.py`, `config.py`, `cli.py`
- `.claude/skills/drum-chart/`: the skill and its references (format, notation, transcribing, grooves)
- `examples/`: non-commercial charts (stress test, synthetic song, the Drum Key)
- `eval/mdb_drums.py`: accuracy on MDB Drums; `tools/build_kit.py`: rebuilds the drum samples

## Commands

```bash
uv run drum-agent doctor                        # test everything
uv run drum-agent run "Artist - Title" --json   # find, fetch, analyze -> draft.drums + draft.html
uv run drum-agent analyze <file-or-slug> --json # analyze audio you have
uv run drum-agent render chart.drums --midi chart.mid
uv run --group dev pytest                       # tests (offline, synthetic audio)
uv run python eval/mdb_drums.py                 # accuracy on 23 annotated recordings
claude plugin validate .                        # plugin manifests
DRUM_AGENT_UPDATE_GOLDEN=1 uv run --group dev pytest tests/test_drumchart.py   # after a deliberate engraving change
```

## Rules

- Never fabricate drum notes. A chart says where its notes come from (`source-kind`) and marks doubt with `@confidence`.
- Notation follows the user's Drum Key picture (`notation: drumkey`, the default); keep `tests/test_drumchart.py` passing.
- Playback uses real recorded drums (GMRockKit, GPL-3.0, `drumchart/assets/kit/NOTICE.md`), never synthesized drums.
- Spotify is metadata only (DRM). YouTube audio is fetched only on the user's machine for their own use.
- Audio, charts of commercial songs and credentials never go into git. Secrets live in
  `~/.config/drum-agent/.env` (written by `drum-agent setup`) and `~/.spotify-mcp/`; never read or print them.
