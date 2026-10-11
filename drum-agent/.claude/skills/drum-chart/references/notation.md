# Notating drums well

Sources: Weinberg, *Guide to Standardized Drumset Notation* (PAS); Gould,
*Behind Bars*; MOLA guidelines; Hal Leonard *Drum Recorded Versions* practice;
Dorico/MuseScore defaults; GrooveScribe. Where sources disagree, the choice
made here is the one that reads best for an intermediate drummer.

## Contents
1. The kind of chart we write
2. Drum key (what the renderer draws)
3. Write out vs. compress
4. Hi-hat
5. Cymbals, hits, stops
6. Fills
7. Feel, tempo and meter
8. Dynamics and cues
9. Count-ins, pickups, endings, fades
10. Common mistakes

---

## 1. The kind of chart we write
A **transcription chart**: exact notes like a Hal Leonard transcription (every
groove, fill, ghost note, hi-hat opening, crash and variation), laid out with
the density-reducing habits of a session chart (road map, section boxes, bar
repeats with counts, cues). The reader should be able to play along with the
record from it, and never have to guess what a repeat sign means.

## 2. Drum key (what the renderer draws)
Hands = stems up, feet = stems down, always (PAS rule).

| sound | position | head / mark |
|---|---|---|
| crash | ledger line above (A5) | x |
| crash 2 / china | B5 | x / heavy x |
| splash | C6 | x |
| hi-hat (sticks) | space above the staff (G5) | x; `o` open, `+` first closed hit after an open, ⌽ half-open |
| ride | top line (F5) | x; bell = diamond |
| high / mid tom | top space / 4th line | normal |
| snare | 3rd space (C5) | normal; ghost = (parentheses); cross-stick = x; rimshot = slashed |
| floor tom | 2nd space (A4) | normal |
| bass drum | 1st space (F4) | normal, stem down |
| hi-hat foot | space below the staff (D4) | x, stem down; `o` below = foot splash |

Accents go outside the beams (above for hands, below for feet). The renderer
prints a key with only the instruments and techniques the song uses.

## 3. Write out vs. compress
* **Write out** any bar that differs from the previous bar by even one note
  (a ghost note, an opening, a missing kick). Intermediate readers trust what
  they see. Make it a separate pattern.
* **Repeat sign** (automatic) for an identical bar; two-bar repeat signs for
  identical 2-bar patterns. Each is numbered with its position in the section,
  phrase ends (4, 8, 12, 16) in bold — that's how readers count long sections.
* A repeat sign never follows a fill or a one-off bar: after a fill, the groove
  is written again (automatic, because the previous bar differs).
* Repeated sections: write each section where it occurs (linear form). No
  D.S./Coda jumps — every jump is a chance to get lost.
* Sections where the drums are silent: `rest N "Drums out — gtr + vox"`. Put a
  cue on the bar where the drums come back.

## 4. Hi-hat
* Closed is the default (no mark). `o` = open; the next closed stroke gets `+`
  automatically. Use `h` for a half-open / "washy" sizzle; if the whole section
  is washy, write `h` throughout or add a section `note "Hi-hat half-open throughout"`.
* An open note that is closed by the foot on the next beat: `HH o` then `HF x`
  at the closing point.
* "Swishy" grunge/punk hats played loosely: still write the rhythm exactly;
  describe the sound in a section note.
* Hi-hat foot with 8ths or quarters under a ride pattern: write it (`HF`), it's
  part of the groove.

## 5. Cymbals, hits, stops
* **Crash on 1** at section starts replaces the hi-hat/ride stroke on that beat
  (`from` pattern with the `CR` row and the first hat removed). Crash + kick
  together is the normal "hit".
* Short hit (band stops dead): choke `k` on the cymbal, then real rests, plus
  `@stop` or `@text "Band stops"`. Long hit: plain `x` and rests; the cymbal
  rings by default (no "let ring" mark needed).
* Fermata over a held hit: `@fermata 3` (beat 3).
* Ride vs. crash-ride: if the drummer rides on a crash, use `CR` for those
  strokes and add `note "Riding on the crash"`.

## 6. Fills
* Every fill written note for note, with the orchestration (which tom), the
  sticking if it's not alternating (`ST` row), flams/drags, and the kick under it.
* Typical fill landings: crash + kick on the next downbeat — that downbeat
  belongs to the next section's first bar (`play chorus-crash`).
* Fills that start mid-bar: the groove continues until the fill starts; write
  the whole bar.
* Pickup fills into the song start: a bar with rests before the fill (`- - - x`
  style), labelled `@text "Fill"`.

## 7. Feel, tempo and meter
* **Straight vs. swung.** Swung 8ths: either write triplets in 4/4 (`x-x` per
  beat: quarter-8th triplet) or the whole song in 12/8 (`time: 12/8`, counts
  "1 & a"). Use 12/8 when the feel is a constant shuffle; triplets in 4/4 when
  it swings only in places. Put the feel in `feel:` ("Shuffle", "Swung 8ths").
* **Half-time feel** (snare on 3 at the same tempo): keep the tempo, add
  `@text "Half-time feel"`. Don't halve the BPM unless the record does.
* **Tempo drift**: live-tracked records (most pre-2000 rock) drift a few BPM.
  Give the average tempo; if a section clearly speeds up, add `@tempo`. Note
  it in `notes:`.
* **Meter changes**: `@time` exactly at the bar. Odd meters always with a
  grouping (`7/8 2+2+3`). A single 2/4 bar inside 4/4 songs is common (often
  before a chorus) — don't absorb it into a 4/4 bar.

## 8. Dynamics and cues
* One dynamic per section change at most (`@dyn mf`), hairpins for builds
  (`@cresc bars=2`). Ghost notes are shown with parentheses, not dynamics.
* Cue text every 2–4 bars where the reader could get lost: instrument entries
  ("Bass in", "Gtr riff", "Vocals in"), section moments ("Build", "Big chorus"),
  and before any stop/hit. Cues name musical events, not lyrics: don't quote
  lyric words, even short fragments (they're copyrighted, and "Vocals in" or
  "Gtr stops" is just as good a landmark).
* Plain English only: "Drums out", "Band stops", "Hold", "Gtr alone". No "N.C."
  on a drum chart.

## 9. Count-ins, pickups, endings, fades
* Audible stick/hi-hat count-in: make it the first section (`section Count-in`)
  with `HF` or `SN` cross-stick quarter notes and `@text "Count-in"`.
* Pickup notes before bar 1: write a full bar with rests before the pickup.
* Fade-out endings: chart the groove until the fade is inaudible, add
  `@text "Fade out"` and `@dim bars=4` over the last line.
* Final hit: write it (crash+kick, choke or let ring) with `@fermata` if held.

## 10. Common mistakes (check before rendering)
* Simplifying a varied section into one repeated pattern ("the chorus is
  basically the same") — make the variant patterns.
* Forgetting the crash on the first bar of a section.
* Bar counts that don't match timestamps (use the summary's timing check).
* Writing hats as 16ths when the record has 8ths (or vice versa) — count the
  hits in the hit map over a few bars before deciding.
* Putting the kick in 8ths when it's actually on the "a" (16th) — zoom into
  the hit map; a kick just before a snare backbeat is usually on the "a".
* Missing the 2/4 or 3/4 bar before a chorus.
