# Transcribing a song's drum part

How to find out what the drummer actually plays, with or without the audio.

## Contents
1. Evidence and confidence
2. Research checklist (always)
3. The listening pipeline (when you have audio)
4. Reading the hit maps and bars.txt
5. Form, tempo and bar arithmetic
6. Section-by-section checklist
7. From draft to finished chart
8. Getting audio (and what not to do)

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
| audio analysis (this skill) | exact tempo map, bar lines, form, kick/snare/hat rhythm, crashes, where fills are | ghost notes under loud guitars, tom pitch, ride vs. crash, hi-hat openness |

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

Read it with `scripts/game_chart.py`:
```
python scripts/game_chart.py notes.mid --form           # sections, bars, start time, avg BPM
python scripts/game_chart.py notes.mid --bars 40-48     # lanes per bar, .drums-style beat groups
python scripts/game_chart.py notes.mid --anim --bars 47 # hands, crash 1/2, ride, hi-hat open, flams
python scripts/game_chart.py notes.mid --offset -3.0    # shift times to the album clock
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
Install once (CPU is fine; ~2 GB with the CPU torch wheel, ~6 GB when only the regular PyPI wheel is reachable):
```
bash scripts/setup_audio.sh          # creates .venv-audio with demucs, beat_this, madmom, ADTOF, librosa
```
Run:
```
.venv-audio/bin/python scripts/analyze_audio.py song.mp3 --out work/ --bpm 117 --title "Lithium" --artist "Nirvana"
```
* `--bpm` (from research) prevents double/half-time beat tracking.
* `--meter 6/8` (or 3/4, 12/8...) if the song isn't in 4/4. For songs that
  change meter, analyse the sections separately with `--start/--end`.
* `--drumsep` additionally splits the drum stem into kick/snare/toms/hi-hat/
  ride/crash. It is **very slow on CPU (~2–3× the audio length)**: only use
  it on a short passage (`--start 1:52 --end 2:10`) when ride vs. crash or a
  tom fill is genuinely unclear — never on a whole song.
* Runtime on a 4-core CPU: about 1–3 minutes per minute of audio, mostly
  demucs. Run one heavy audio job at a time; parallel torch jobs crawl.

Outputs (in `work/`): `report.md`, `bars.txt`, `activations.txt`,
`draft.drums`, `maps/*.png`, `analysis.json`, `drums.wav`.
Toms are split by pitch automatically (report: "toms: split by pitch: FT ~105
Hz, T1 ~144 Hz"); check the assignment in fills. `activations.txt` shows the
detector's confidence at every grid slot even below its threshold — the best
place to find ghost notes (snare-row 1–3s between backbeats) and quiet hits.

What to expect from the automatic draft, before any correction (F1 per
instrument family):

| test | kick | snare | hi-hat | cymbals | toms | overall | ghosts found |
|---|---|---|---|---|---|---|---|
| 40-bar test song, real acoustic-kit samples, full mix | 0.94 | 0.92 | 1.00 | 0.99 | 0.99 | 0.98 | 7 % |
| 23 real multitrack recordings (MDB Drums), demucs stem | 0.86 | 0.62 | 0.88 | 0.42 | 0.42 | 0.79 | ~5 % |

Tempo, bar lines and the section form were exact on the test song. On real
records: trust kick/hi-hat/crash rhythms, check snare carefully, **check every
fill for toms** (often missed or called kick/snare), and add ghost notes
yourself — the detector's `?` candidates catch most of them but are mostly
false alarms (≈25 % precision), so confirm each one in the spectrogram and
against lessons. Treat hi-hat openings as hints.

## 4. Reading the hit maps and bars.txt
**maps/map_NNN-MMM.png** — 4 bars per image:
* Top: spectrogram of the drum stem. Kick = bright blob at the very bottom.
  Snare = vertical stripe through the middle (bright 150–400 Hz + noise up
  high). Toms = shorter blobs at 80–300 Hz with a pitch you can see (higher tom
  = higher blob). Closed hi-hat = thin short ticks at the top. Open hi-hat /
  crash = high-band smear that lasts (crash longest and broadest, with a strong
  attack across all bands). Ride = regular ticks at the top with a continuous
  shimmer between them; bell = a narrow bright line in the middle-high range.
* Bottom: detected hits on lanes, on the bar/beat/subdivision grid. Marker
  size and opacity = loudness. Diamonds = hi-hats flagged as open.
* Check: is every spectrogram stripe a dot? Is every dot a real stripe?
  Fills show up as dense dots on the snare/tom lanes just before a blue barline.

**bars.txt** — the same per bar as text, one row per class, beats separated
by spaces, digits = loudness 1–9 relative to that instrument (1–3 ghost
range, 8–9 accents), `o` = open hi-hat:
```
bar  17  0:33.41   117.3 bpm  [B1]
   CR  9--- ---- ---- ----
   HH  ---- 6-5- 6-5- 6-5-
   SN  ---- 9--2 ---- 9---
   BD  8--- --7- 8-7- ----
```
Use it to decide each bar's pattern precisely, then confirm on the image.

Typical machine errors and how to spot them:
* **Snare ghost notes missed** under distorted guitars: look for faint snare
  stripes in the spectrogram between backbeats; check lessons.
* **Floor tom labelled kick** (or vice versa): floor-tom blobs sit higher and
  ring longer; in fills, low hits between snare hits are usually floor tom.
* **Crash labelled hi-hat open** or ride: crash smear covers almost the whole
  height and lasts > 1 s.
* **Flams merged** into one hit: a flam looks like a slightly doubled stripe.
* **Hi-hat 8ths vs. 16ths**: count hat ticks over two beats in the image.
* **Bar line off by one beat** (downbeat phase wrong): the backbeat snare
  should be on beats 2 & 4; if it's on 1 & 3 everywhere, shift the bars.
* Grid fit in `report.md` > 6% of a beat = loose playing or wrong tempo/meter.

## 5. Form, tempo and bar arithmetic
* bars = seconds × BPM ÷ 60 ÷ beats per bar. At 120 BPM in 4/4 a bar is 2.0 s.
* Use the analysis bar numbers and timestamps; section boundaries are where
  the spectrogram texture changes, crashes land, and fills end.
* Sections are usually 4, 8, 12 or 16 bars. Odd lengths do happen (2-bar
  extensions, a 2/4 bar, pickups, a riff of 6) — confirm them in the map.
* `render_chart.py` prints each section's computed start time; give every
  section `at m:ss` from the recording and fix any drift > 4 s it reports.

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
`draft.drums` has one pattern per distinct detected bar (p1, p2, ...) and
sections A1, B1, A2... from the automatic form. To finish it:
1. Rename sections (Intro, Verse 1, Chorus 1...) and fix boundaries.
2. Merge patterns that differ only by detection noise (a stray hat, a
   missing ghost note) into the true pattern — but keep real variations.
3. Rename patterns musically (`verse`, `verse-fill`, `chorus-crash`).
4. Add what the machine can't: cross-stick vs. snare, ride bell, chokes,
   flams, tom identities, open-hat lengths, sticking for fills.
5. Add cues, dynamics, section notes, `confidence`.
6. Render, compare the timing summary with the recording, look at the PNG.

## 8. Getting audio (and what not to do)
* Use audio the user gives you (an upload or a file path), or audio they
  legitimately own or license. Official 30-second previews are fine for a
  quick tempo/groove check where reachable.
* Don't download songs from YouTube rippers or piracy sites, even if a tool
  could; ask the user for the file instead.
* No audio → chart from research, mark confidence honestly, and offer to refine
  the chart when the user provides the recording.
