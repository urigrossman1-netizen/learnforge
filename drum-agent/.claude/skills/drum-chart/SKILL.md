---
name: drum-chart
description: Listen to a song and write its drum chart. Finds the song (Spotify for details, YouTube or the user's own file for audio), transcribes the drums from the audio, and turns the result into an easy-to-read, zoomable, playable chart in the user's Drum Key notation (engraved staff, counts, colour hit grid, real drum sounds, MIDI, PDF). Use whenever the user asks for a drum chart, drum transcription, drum sheet music, drum notation or tab, "what does the drummer play", grooves or fills of a specific song, or to analyze an audio file's drums, even if they only name the song ("chart Lithium", "drums for Back in Black"). Also for editing, fixing, re-rendering or exporting an existing .drums chart or chart page.
---

# Drum chart

You produce the chart a professional transcriber would: complete (first drum
hit to last, every fill, stop and variation), honest about what is certain,
and easy for an intermediate drummer to read. The audio analysis hears the
drums; you organise, check and present what it heard. **Never invent notes**:
every hit in a chart comes from the analysis, from evidence you can name
(research, a beat-mapped game chart, the user), or is marked uncertain.

## The toolkit

Run everything with `drum-agent <command>`. It is on PATH when the drum-agent
plugin is enabled. Otherwise use `${CLAUDE_SKILL_DIR}/../../../bin/drum-agent`
(inside a checkout of the drum-agent repo; on Windows `bin\drum-agent.cmd`). If
neither exists, install it once:
`git clone --depth 1 https://github.com/urigrossman1-netizen/drum-agent ~/.drum-agent`
and use `~/.drum-agent/bin/drum-agent`. It needs `uv`
(https://docs.astral.sh/uv/); the first command installs the Python
dependencies, which takes 1-3 minutes. Say so the first time.

Songs and charts live in the user's library: `~/DrumAgent` (or `$DRUM_AGENT_HOME`;
inside the drum-agent repo itself, the repo folder). Every command prints the
paths it wrote; use those, and add `--json` when you need to parse them.

| file | what it is |
|---|---|
| `references/format.md` | the `.drums` chart format: instruments, articulations, patterns, sections, directives. **Read before writing or editing a chart.** |
| `references/transcribing.md` | evidence and confidence, research checklist, game charts, reading the draft, bar arithmetic, getting audio |
| `references/notation.md` | how to notate drum things well: what to write out vs compress, hi-hat openings, fills, feels, odd meters |
| `references/grooves.md` | correctly notated patterns for common styles, as starting points |

## Workflow

### 1. Pin down the job
Song, artist, which version (album, live, remaster), and what the user wants.
Default: the complete drum part as a chart page. If the user gave an audio
file, that recording is the reference.

### 2. Identify the song
Spotify MCP if connected: `mcp__spotify__search` (`types: "track"`, `limit: 5`),
then `mcp__spotify__get_track` for duration and album. The tool names may carry
a plugin prefix (e.g. `mcp__plugin_drum-agent_spotify__search`). Without it:
`drum-agent search "Artist - Title" --json` (also gives the release year).
If both fail, continue with what the user said and YouTube's metadata.

### 3. Get the audio
* **The user's file** (upload, attachment, path, Google Drive download): use it.
* **YouTube** (the user has given permission for their personal use): pick the
  upload with the YouTube MCP (`ytdlp_search_videos`, `maxResults: 8`): duration
  within ~3 s of Spotify's, prefer "Artist - Topic" or "Official Audio", avoid
  live, cover, remix, karaoke, sped-up, drumless and long-intro videos. Then
  `drum-agent run --title "<t>" --artist "<a>" --duration <s> --url "<url>" --json`.
  Without the MCP, `drum-agent run "Artist - Title" --json` searches and ranks itself.
* Audio stays in the user's library. Never commit, upload, publish or share it.
  Never try Spotify audio (DRM) or piracy sites.
* **Cloud session** (YouTube/Spotify are usually blocked there; `drum-agent
  doctor` shows it): ask for the file (upload or Google Drive), or offer a
  research-only chart and say clearly that it is not transcribed from the audio.

For a file: `drum-agent analyze "<path>" --title "<t>" --artist "<a>" --json`.
Many songs: one `Artist - Title` per line in a file, `drum-agent batch <file> --json`.

### 4. Check the analysis, re-run if needed
Open `draft.drums` (and `analysis.json` for details). Fix the grid first, by
re-running `drum-agent analyze <slug> <flags> --json` (no new download):

| symptom | add |
|---|---|
| tempo is half or double what the song feels like | `--bpm <right tempo>` |
| backbeat snare on 1 and 3 in a rock/pop/funk groove | `--shift-beats 1` (or `3` if crashes then land on beat 3) |
| kick only on beat 3, crashes and fills land mid-bar | `--shift-beats 2` |
| the song is in 3/4 | `--beats-per-bar 3` |
| 6/8 (reported BPM = dotted-quarter pulse, 2 per bar) | `--beats-per-bar 2 --subdivision 3` (if the BPM is ~3x that, also `--bpm <BPM/3>`) |
| 12/8 or a shuffle: hats and kicks smear across `e` and `a` | `--beats-per-bar 4 --subdivision 3` |
| the user has an isolated drum track | `--drum-stem <file>` |

Use your knowledge of the song only to *check* tempo, meter and form against the
analysis, never to replace detected notes.

### 5. Write the chart
Copy `draft.drums` to `chart.drums` in the same folder and improve it (details in
`references/transcribing.md` §7):
* Section names (Intro, Verse 1, Chorus 1, ...) where the structure, energy and
  research support them; otherwise keep Part A / Part B. Same letter = same material.
* Merge patterns that differ only by detection noise; keep every real variation
  as its own pattern (a repeat sign must mean "exactly the previous bar").
* Add what the machine cannot hear only with evidence, and mark it:
  toms in fills, ride vs hi-hat, open hats, cross-stick, bell, chokes, flams,
  ghost notes, sticking → `@confidence medium "lesson + game chart"`.
* Keep every `@confidence` the analysis set unless you resolved it (say how in a
  `note`). Keep `source-kind: audio` and the transcriber line truthful.
* Cues every few bars naming musical events (vocals in, guitar riff, band stops,
  solo), never lyrics. Dynamics at section changes. Fills marked `@fill`.

### 6. Render, check, look
```
drum-agent render chart.drums --midi chart.mid      # chart.html + form/timing summary
drum-agent render chart.drums --pdf chart.pdf --png chart.png   # needs Playwright Chromium
```
Fix every error (they give the line and the fix). Compare the summary with the
recording: total length, and section starts vs `at` times (it warns at > 4 s).
If you can, look at the PNG: fills readable, nothing colliding, repeat signs
only where bars are really identical.

### 7. Deliver
Give the paths to `chart.html` (open it: zoom, play with real drum sounds,
loop a section, slow down), `chart.mid`, the PDF if made, and where the audio is.
If the session can publish artifacts, publish `drum-agent render chart.drums
--artifact -o chart.artifact.html` so it opens on any device (the page carries
its own chart source; `drum-agent extract page.html` turns any chart page back
into an editable chart). In a cloud session copy the deliverables into the
user's project or publish them, since the container is temporary.
In your message: tempo, meter and form in one line; what is solid; what is marked
uncertain and why; what to check by ear. Never say you "listened" to a song you
charted from research only.

## Setting up
When the user asks to set up the drum agent, or a command reports something
missing: run `drum-agent setup --non-interactive`, then `drum-agent doctor`, and
report the result in plain words. Spotify keys are optional. To add them, give
the user the exact command for their own terminal (`command -v drum-agent` shows
the launcher's full path; on Windows `bin\drum-agent.cmd` in the plugin folder)
followed by ` setup`: it explains where to get the keys and stores them outside
every repository. Don't ask the user to paste keys into the chat; if they do,
run `drum-agent setup --spotify-client-id ... --spotify-client-secret ...` and
don't repeat the values.

## Editing an existing chart
Edit the `.drums` file (or `drum-agent extract` it from a page first), keep the
old version (`chart.v2.drums` or git), re-render, and tell the user what changed.
User corrections are the strongest evidence: apply them exactly, drop the
corresponding `@confidence` mark, and look for the same mistake elsewhere.

## Research-only charts (no audio)
When there is no audio: research the part (lessons, interviews, tempo databases)
and look for a beat-mapped rhythm-game chart (`references/transcribing.md` §2,
`drum-agent game-chart notes.mid --form`). Write `source-kind: research`, a
transcriber line "Charted from research ... not transcribed from the recording",
and confidence marks everywhere evidence is thin. Never copy published
transcriptions or game files; write the part in your own notation.

## Honesty and limits
* Grade evidence: high = clear in the analysis or several sources agree;
  medium = one source or partial evidence; low = educated guess. Marked bars get
  a dashed outline and a note on the page.
* The built-in analysis hears kick, snare, hi-hat/ride and crash. It does not
  separate toms, puts the ride on the hi-hat row, rarely hears open hats and misses
  most ghost notes; jazz, brushes and swing are much less accurate. Say so when it
  matters, and suggest a drum stem.
* Lyrics are off-limits in charts, notes, queries and replies.
* If a command fails, run `drum-agent doctor` and report its result instead of guessing.
