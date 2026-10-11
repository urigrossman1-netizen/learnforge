# Transcribing a song's drum part

How to find out what the drummer actually plays, with or without the audio.

## Contents
1. Evidence and confidence
2. Research checklist (always)
3. The listening pipeline (when you have audio)
4. Reading the draft against the recording
5. Form, tempo and bar arithmetic
6. Section-by-section checklist
7. From draft to finished chart
8. Getting audio

---

## 1. Evidence and confidence
You cannot hear. You can (a) read what others have documented and (b) measure
the audio with the analysis tools and *look* at it. Combine both; neither
alone is enough:

| evidence | good for | weak at |
|---|---|---|
| tempo databases (songbpm, tunebat, getsongbpm) | BPM, key, length | half/double-time confusion |
| Wikipedia, album credits | version, drummer, length, recording facts | the part itself |
| lessons (Drumeo, YouTube lesson pages, drum magazines), transcription previews (Musicnotes, Hal Leonard, Songsterr) | groove per section, famous fills | bar-exact form, small variations |
| drummer interviews | intent, kit, technique | details |
| audio analysis (`drum-agent analyze`) | tempo, bar lines, form, kick/snare/hat rhythm, crashes, where fills are | toms, ride vs. hi-hat, hi-hat openness, ghost notes |

Confidence per section/bar: **high** = audio shows it clearly or several
sources agree; **medium** = one source or partial evidence; **low** = guess.
Write it into the chart (`confidence`, `@confidence`). Never present research-
only charts as "transcribed from the recording".

## 2. Research checklist (always)
Search, in this order, and keep URLs:
1. `"<song>" <artist> bpm` → tempo, key, length (check 2–3 sites; if they
   disagree by ×2, the slower/faster reading depends on where the snare falls —
   rock backbeat on 2 & 4 decides).
2. `"<song>" drum lesson` / `drum cover breakdown` / `drum transcription` →
   groove descriptions per section, fills, signature moments.
3. `"<song>" song structure` / annotated song breakdowns → form and timestamps
   (verify with audio when you have it). Vocal timing can tell you where
   sections start; never copy lyric words into the chart or your notes.
4. Wikipedia article for the song and the album → version, length, recording,
   drummer, anything unusual (tempo changes, odd bars).
5. Interviews with the drummer about the song.
6. Rhythm-game charts (Rock Band / Guitar Hero / Clone Hero `notes.mid` +
   `song.ini`, or `.chart`): see "Game charts" below.
Write down what each source says, and where they disagree.

### Game charts
Beat-mapped to the master recording by the charter, so they give the **tempo
map, section markers, bar counts and the rhythm of every bar**. How to find one:
* search GitHub / the web for `"<song>" notes.mid`, `"<artist>" "<song>" song.ini`
  or `"<song>" .chart clone hero`; fan song packs and converted Rock Band DLC
  folders are common. Fetch only `notes.mid`/`notes.chart` and `song.ini`
  (raw file URLs), never the audio.
* prefer `charter = Harmonix` (Rock Band: pro-drums tom/cymbal markers and a
  drummer-animation track), then Neversoft (Guitar Hero), then fan charts.
  `pro_drums = True` in `song.ini` means cymbals and toms are separated.
* check the version: titles like "(Live at Reading)" or "(Rerecorded)" are not
  the album. A live chart can still confirm groove shapes; say so in the chart.

Read it with `drum-agent game-chart`:
```
drum-agent game-chart notes.mid --form           # sections, bars, start time, avg BPM
drum-agent game-chart notes.mid --bars 40-48     # lanes per bar, .drums-style beat groups
drum-agent game-chart notes.mid --anim --bars 47 # hands, crash 1/2, ride, hi-hat open, flams
drum-agent game-chart notes.mid --offset -3.0    # shift times to the album clock
```
Lanes: `KICK SNARE`, cymbals `Y-CYM` (hi-hat) `B-CYM` (ride) `G-CYM` (crash),
toms `Y-TOM` (high) `B-TOM` (mid) `G-TOM` (floor). Charters bend the lanes: in
crash-heavy parts a second crash sits on the yellow or blue cymbal; an open
"washy" hat may be on the blue cymbal; a snare + tom on the same 16th is
usually a flam; two crashes at once on 1 is a double crash. The animation
track settles these. Things a game chart never has: hi-hat openings (except in
the animation), ghost notes, rimshots/cross-stick, dynamics (except accent
and ghost markers on newer charts).

Album clock: game audio usually has 2–4 s of lead-in. Estimate the offset
from `song.ini` `song_length` minus the album length, or from one event you
know on the album (first vocal, a famous hit), then use `--offset`.

Policy when sources disagree: two independent lessons that agree beat the
game chart (they heard the record); otherwise the game chart beats a single
lesson on rhythm and placement. Write the choice and the alternative in the
section's `confidence` note.

Video lessons: a YouTube transcript tool (if the session has one) gives you
what the teacher says — often the best source for grooves and fills. Those
transcripts also catch the sung lyrics while the song plays: skim past them,
keep only the drum explanations, and never echo lyric text in anything you
write (notes, charts, queries, replies). Prefer lesson videos over covers and
play-throughs, which are mostly lyrics.

## 3. The listening pipeline (when you have audio)
```
drum-agent analyze song.mp3 --title "Title" --artist "Artist" --json      # a file you have
drum-agent run --title "Title" --artist "Artist" --url "<youtube url>" --json   # fetch + analyze
```
* `--bpm 117` when the detected tempo is half or double what the song feels like
  (research or the snare placement decides; see the SKILL's fix table).
* `--beats-per-bar 3` for 3/4; `--beats-per-bar 2 --subdivision 3` for 6/8;
  `--beats-per-bar 4 --subdivision 3` for 12/8 or a triplet shuffle.
* `--shift-beats N` when beat 1 is in the wrong place (backbeat on 1 and 3).
* `--drum-stem drums.wav` when the user has an isolated drum track: much better.
* Re-run on the same song without downloading again: `drum-agent analyze <slug> ...`.

What it writes in `charts/<slug>/` (the JSON output lists the paths):
* `draft.drums`: the detection as an editable chart (one pattern per distinct bar,
  repeats collapsed, sections Part A / Part B / Part A 2 by sound, fills marked,
  doubtful bars carrying `@confidence` with the reason). Read it like a chart.
* `draft.html`: that draft engraved; open it, look at it, play it.
* `analysis.json`: tempo (`bpm`, `bpm_min/max`, `bar_restarts`), `bars` (per-bar
  hits as `[step, velocity]` on the grid, `groove`, `fill`, `partial`, `inferred`),
  `grooves` (consensus patterns), `sections` (`label`, `energy_db`, `crash_bars`).
* `performance.mid`: the detected hits timed like the recording, for a DAW.

What the built-in detector hears (measured on MDB Drums, 23 real recordings with
hand-annotated hits; rock/pop/funk/metal subset, full mix): kick F1 0.95, snare
0.77, hi-hat 0.66; tempo right 93%, bar 1 right 93%. Jazz, brushes and swung
ride grooves are much weaker. It does not separate toms (they show up as snare or
kick in fills), puts the ride on the hi-hat row, rarely hears hi-hat openings and
misses most ghost notes. So: trust the kick/snare/hat rhythm and the form; check
every fill, every crash and every section start by ear or against research.

## 4. Reading the draft against the recording
* Steps count grid positions from 0 within the bar, so beat 1 is step 0; with
  16ths, beat 2 = 4, beat 3 = 8, beat 4 = 12; with a triplet grid beat n starts
  at step 3(n-1). A typical hit has velocity 0.7; ≥ 0.95 is an accent; a snare
  below 0.35 is a ghost note (only the snare's loudness is written as dynamics).
* Same letter = same material: Part A and Part A 2 sound alike (groove, energy,
  harmony). Decide what they are (verse, chorus...) from the structure, the energy
  (`energy_db`, crashes) and research; until then keep the neutral name.
* `inferred` hi-hats were restored under the snare (the snare hides them);
  `partial` bars are where the count restarts (a stop, a pickup, a 2/4 bar).
* Typical machine errors: a floor tom heard as kick, high toms heard as snare,
  a crash heard as an accented hat, flams merged into one hit, 8th vs 16th hats
  confused under distortion, the bar line one or two beats off after a stop.

## 5. Form, tempo and bar arithmetic
* bars = seconds × BPM ÷ 60 ÷ beats per bar. At 120 BPM in 4/4 a bar is 2.0 s.
* Use the analysis bar numbers and timestamps; section boundaries are where
  the spectrogram texture changes, crashes land, and fills end.
* Sections are usually 4, 8, 12 or 16 bars. Odd lengths do happen (2-bar
  extensions, a 2/4 bar, pickups, a riff of 6) — confirm them in the map.
* `drum-agent check chart.drums` prints each section's computed start time; give
  every section `at m:ss` from the recording and fix any drift > 4 s it reports.

## 6. Section-by-section checklist
For each section, decide and write down:
1. Time-keeping voice: closed hat / open-washy hat / ride / crash-ride / floor tom.
   8ths or 16ths or quarters?
2. Snare: backbeat (2 & 4), half-time (3), every beat, cross-stick? Ghost notes?
3. Kick pattern: write the most common bar, then the variants (often bar 4 or 8).
4. First bar: crash on 1? (Almost always at choruses.)
5. Last bar: fill? Which beats, which drums, sticking, does it end with a
   crash into the next section?
6. Variations between repeats (Verse 1 vs. Verse 2, Chorus 1 vs. Chorus 3):
   compare the maps of both — don't assume they're the same.
7. Dynamics: quieter verse, building pre-chorus, big chorus? Hairpins?
8. Stops, breaks, held hits, pickups, tempo or meter changes.
9. Cues: where vocals/guitar enter, stops, solos (musical events, not lyrics).

## 7. From draft to finished chart
`draft.drums` has one pattern per distinct detected bar (`groove-a`, `groove-a-2`,
`fill`, ...) and sections Part A, Part B, Part A 2 from the automatic form. To finish it,
copy it to `chart.drums` and:
1. Name sections (Intro, Verse 1, Chorus 1...) only with evidence (structure,
   energy, research); otherwise keep the neutral name. Fix boundaries.
2. Merge patterns that differ only by detection noise (a stray hat, a missing
   ghost note) into the true pattern, but keep real variations.
3. Rename patterns musically (`verse`, `verse-fill`, `chorus-crash`).
4. Add what the machine can't hear, from evidence: tom identities in fills,
   ride vs hi-hat, open hats, cross-stick, ride bell, chokes, flams, ghost
   notes, sticking. Mark each such addition `@confidence medium|low "why"`
   unless several sources agree.
5. Add cues, dynamics, section notes and `confidence`. Never delete a flag
   the analysis raised without saying why in a note.
6. Render, compare the timing summary with the recording, look at the page.

## 8. Getting audio
* Best: a file the user gives you (upload, attachment, path, Google Drive).
* With the user's permission, `drum-agent fetch`/`run` saves the song from YouTube
  on the user's own machine for their personal practice and analysis. The audio
  stays in their library folder (`audio/`): never commit, upload, publish or share it.
* Spotify is for song details only; its audio is DRM-protected. Never use piracy
  sites or "stream rippers".
* Cloud sessions usually cannot reach YouTube or Spotify. Ask the user to upload
  the file (or put it in Google Drive), or to run the agent on their own computer.
* No audio at all → chart from research (`source-kind: research`), say so on the
  chart and in your reply, and offer to refine it when they provide the recording.
