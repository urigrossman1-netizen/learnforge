---
name: drum-chart
description: Write a drum chart for a song. Finds the song on Spotify (metadata) and YouTube (audio source), acquires the audio locally, transcribes the drums, and turns the analysis into a readable chart with road map, grooves and fills. Use whenever the user asks for a drum chart, drum transcription, drum part, groove, fills or "how do I play the drums on <song>", including for several songs or a playlist.
---

# Drum chart

Machine analysis gives timing, bar counts and hit positions. Your job is to
turn it into a chart a drummer can read, without inventing notes the
analysis does not contain. Run every command from the `drum-agent/` folder.

## 1. Identify the song (Spotify MCP)

Call `mcp__spotify__search` with `query: "<artist> <title>"`, `types: "track"`,
`limit: 5` (Spotify caps search at 10). It returns lines like
`Title by Artist (ID: <id>)`. Pick the studio version that matches the request
and call `mcp__spotify__get_track` with that ID for album, duration (M:SS) and
URL. The release year arrives later in `run --json` (`meta.spotify.release_date`).

- The first Spotify MCP call opens a one-time browser login. If the Spotify
  MCP is unavailable or not logged in, run
  `uv run drum-agent search "<artist> - <title>" --json` instead (same Spotify
  app keys, no login; it also returns the release date).
- If neither works, continue with YouTube metadata only and say so.

## 2. Choose the audio source (YouTube MCP)

Call `mcp__youtube__ytdlp_search_videos` with `query: "<artist> - <title>"`,
`maxResults: 8`, `response_format: "json"`. Pick the upload whose duration is
within about 3 seconds of the Spotify duration, preferring an
`Artist - Topic` channel or an "Official Audio" upload. Avoid live, cover,
remix, karaoke, slowed/sped-up, "drumless" and lyric videos with long intros.
If the user supplied an audio file, skip this step and use the file.

Never try to get audio from Spotify: its streams are DRM-protected.

## 3. Acquire and analyze

```bash
uv run drum-agent run --title "<title>" --artist "<artist>" --duration <seconds> --url "<youtube url>" --json
```

For a file the user already has: `uv run drum-agent chart "<path>" --title "<title>" --artist "<artist>" --json`.
For a list of songs, write one `Artist - Title` per line to a file and run
`uv run drum-agent batch <file> --json`, then do steps 4-5 for each song.

Outputs in `charts/<slug>/` (the slug is printed in the JSON): `analysis.json`
(data), `chart-draft.md` (machine draft), `drums.mid` (General MIDI, channel
10), `meta.json` (sources). Downloaded MP3s are in `audio/`.

## 4. Sanity-check the analysis, re-run if needed

Read `analysis.json`: `tempo` (including `bar_restarts`), `sections`, `grooves`
(consensus pattern per groove), and `bars` (per-bar hits as `[step, velocity]`,
`groove`, `fill`, `section`, and `partial` for incomplete bars). Steps count
grid positions from 0 within the bar, so beat 1 is always step 0. With 4/4 and
16ths: beat 2 = 4, beat 3 = 8, beat 4 = 12. With `--subdivision 3`: beat n
starts at step 3(n-1). A typical hit has velocity 0.7; >= 0.95 is an accent,
a snare below 0.35 is a ghost note.

| Symptom | Fix (add to the same `chart` command) |
|---|---|
| Tempo is half or double what the song feels like | `--bpm <correct tempo>` |
| Main groove has the backbeat snare on 1 and 3 (rock/pop/funk) | `--shift-beats 1` (or `3` if crashes then land on beat 3) |
| Kick only on beat 3 and crashes/fills land mid-bar | `--shift-beats 2` |
| Song is in 3/4 | `--beats-per-bar 3` |
| Song is in 6/8 (reported BPM = dotted-quarter pulse, 2 per bar) | `--beats-per-bar 2 --subdivision 3`; if the BPM is about 3x that (eighth notes), also `--bpm <BPM/3>` |
| 12/8 or a shuffle: hats and kicks smear across `e` and `a` | `--beats-per-bar 4 --subdivision 3` |
| User has an isolated drum track | `--drum-stem <file>` |

Re-run without downloading again: `uv run drum-agent chart <slug> <flags> --json`
(this works for fetched songs and for files the user gave you; saved Spotify
and YouTube details are kept). Use your knowledge of the song to judge feel
and form, but take bar counts, tempo and hit positions from the analysis.

## 5. Write `charts/<slug>/CHART.md`

Use this structure. Keep tabs exactly as the analysis gives them; mark
anything you inferred or that the analysis flags (`inferred`, `partial`,
low-velocity notes, one-off bars) as "check by ear". The meter in the header
comes from the draft (`4/4`, `3/4`, `6/8`, `12/8`).

````markdown
# <Title> — <Artist>
<Album> (<year>) · ♩ = <bpm> · <meter> · <feel: straight 8ths / 16ths / shuffle / half-time> · <length>

## Road map
| Section | Bars | Starts | Groove | Notes |
|---|---|---|---|---|
| Intro | 1–4 (4) | 0:00 | A | crash on 1; hat only first 2 bars |
| Verse 1 | 5–20 (16) | 0:09 | A | fill bar 20 |
| Chorus | 21–28 (8) | 0:44 | B | crash every 4 bars |
...

## Grooves
### A — Verse groove
<one sentence: hat pattern, kick placement, backbeat, anything notable>
```text
     1 e & a 2 e & a 3 e & a 4 e & a
HH | x . x . x . x . x . x . x . x . |
SN | . . . . o . . . . . . . o . . . |
BD | o . . . . . o . o . . . . . . . |
```

## Fills
### Bar 20 → Chorus
```text
...
```

## Performance notes
- Dynamics, crash placement, stops/breaks, feel, count-in.
- What to verify by ear (toms, ghost notes, open hats, ride, anything flagged).

Legend: x cymbal · o drum · X/O accent · g ghost · . rest
````

Section names (Intro/Verse/Pre-chorus/Chorus/Bridge/Solo/Outro): use the
section `label` (same letter = same material), position in the song,
`energy_db` (louder + crashes usually = chorus) and your knowledge of the
song. If unsure, keep the letter and say so. A bar count restart
(`bar_restarts` > 0) usually marks a stop or break: write it in the road map.

## 6. Report back

Give the paths to `CHART.md`, `drums.mid` and the MP3, the tempo and form in
one or two lines, and what the user should double-check by ear. If a command
failed, run `uv run drum-agent doctor` and report its result instead of guessing.

## Limits to state when relevant

- Toms are not separated, with or without a stem: fills show toms as snare or
  kick. Ride patterns appear on the HH row. Open hats and ghost notes are often
  missed. On a full mix, bass notes can add kicks and guitars can add snares;
  a drum stem (`--drum-stem`) helps with both.
- Jazz, brushes and ride-led or swung grooves are much less accurate than
  rock, pop, funk and metal.
- Audio is for the user's own practice and analysis: it stays in `audio/`
  (git-ignored). Do not commit or share it.
- If YouTube answers "Sign in to confirm you're not a bot", run
  `uv run drum-agent setup --cookies-from-browser firefox` (the user must be
  logged in to YouTube in that browser; on Windows Chrome/Edge cookies only
  work with the browser closed), then reconnect the youtube MCP server
  (`/mcp`) before searching again. `drum-agent run` picks it up immediately.
