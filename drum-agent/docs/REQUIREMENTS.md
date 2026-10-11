# Requirements and decisions

What the user asked for across the drum chats, how it is met, and what is still open.
Status: **done**, **partial** (works with stated limits), **open**.

## Decisions the user made

| decision | source | how it applies |
|---|---|---|
| Fetch songs from YouTube and listen to them | "You search the song, download the MP3 or WAV, and listen to it really well"; "I'm giving you my permission to use my Spotify and YouTube" | `drum-agent run/fetch` use yt-dlp **on the user's own machine** for their personal practice and analysis. Audio stays in their library, is never committed, uploaded or shared. Spotify is used for song details only (its audio is DRM-protected). Piracy sites are never used. This overrides the earlier chart skill's "never download from YouTube" rule. |
| Notation like the Drum Key picture | "the drum charts are supposed to be like the picture" | default staff key `drumkey`; tested against positions measured from the picture |
| Real drum sounds | "All the sounds are supposed to be from real sounds" | GMRockKit recordings for all playback |
| Staff + count/colour grid, intermediate level | readability chat | every chart page |
| One repo for everything drum-agent | "Make another repo, especially for the Drum agent thing" | this repository, also a Claude Code plugin |
| Local, single user; Claude optional | architect chat | runs on the user's machine; Claude orchestrates through the skills |

## Requirements

| # | requirement | status | where |
|---|---|---|---|
| P0 | accept real audio (file or song name); clear errors for bad input | done | `audio.inspect`, `pipeline`, plain `error:` lines |
| P1 | actually process the audio | done | `transcribe.py`, `job.json` |
| P2 | tempo, beats, downbeats, bars; half/double-time correction; meters | partial | detected tempo map and downbeats; half/double and 3/4, 6/8, 12/8 are set with flags the skill chooses (`--bpm`, `--beats-per-bar`, `--subdivision`) |
| P3 | isolate / analyze the drums | partial | soft harmonic/percussive separation; `--drum-stem` for a user's stem; no neural separator built in |
| P4 | structured drum events (raw time, grid position, velocity, confidence) | partial | `analysis.json` per-bar hits with velocity on the grid; raw times are kept only at bar level |
| P5 | events → real chart | done | `draft.py` → `.drums` |
| P6 | display correctly: readable, zoomable, real notation | done | `drumchart/` page |
| P7 | user correction: add/remove/move hits, undo/redo, versions | done (CLI/Claude) | `drum-agent bar --set`, `history/undo/redo/restore`, `diff`; no click-to-edit in the page |
| P8 | export | done | HTML page (with embedded source), PDF, PNG, chart MIDI, performance MIDI, `.drums` |
| P9 | failures and long songs | done | input checks, job records, 7-minute songs tested |
| P10 | accuracy, measured | partial | MDB Drums evaluation; see README "How well it listens" |
| — | every element: kick, snare, hi-hat open/closed, ride, crash, china, splash, toms, cross-stick, ghosts, accents | partial | the notation, playback and MIDI support all of them; what the automatic transcriber can hear is listed in README with measured numbers; the rest comes from evidence and is marked |
| — | no fabrication; provenance; honest confidence | done | `source-kind`, `@confidence`, skill rules |
| — | play along with the recording | done | "Load song…" in every chart page |
| — | usable from any future project | done | Claude Code plugin + repo-in-picker for cloud sessions |
| — | "make the art": a page explaining how the agent works | done | published explainer page (see the final report) |
| — | spoken "real voice" for the agent | open | the request was ambiguous (drum sounds were built; spoken output was never confirmed) |
