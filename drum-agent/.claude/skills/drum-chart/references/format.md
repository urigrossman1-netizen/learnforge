# The `.drums` chart format

A `.drums` file is plain text: a header, named **patterns** (grooves, fills),
and **sections** that play those patterns in order. The renderer turns it into
engraved notation plus a count grid. Write it top to bottom like a lead sheet.

## Contents
1. Header
2. Instrument rows and the grid
3. Characters (articulations)
4. Patterns
5. Sections and statements
6. Directives (`@...`)
7. Meters, tuplets and counting
8. Worked example
9. Validation errors and how to fix them

---

## 1. Header

`key: value` lines before the first `pattern` or `section`.

| key | meaning | example |
|---|---|---|
| `title` | song title (required) | `title: Lithium` |
| `artist` | performer | `artist: Nirvana` |
| `album` | album and year | `album: Nevermind (1991)` |
| `drummer` | drummer on the recording | `drummer: Dave Grohl` |
| `tempo` | starting tempo in quarter notes per minute; add `q.`/`h`/`e` for other units | `tempo: 117` / `tempo: 64 q.` |
| `time` | starting time signature (`7/8 2+2+3` for groupings) | `time: 4/4` |
| `feel` | style word printed with the first tempo mark | `feel: Straight 8ths` |
| `length` | length of the recording (shown, and compared with the chart) | `length: 4:17` |
| `per-line` | bars per line (default 4) | `per-line: 4` |
| `restate` | `section` (default: a groove is written once per section, then repeat signs) or `system` (rewrite it at the start of every line) | |
| `counting` | `beats` or `eighths` for x/8 meters | |
| `notation` | staff key: `drumkey` (default, the user's Drum Key picture) or `pas` (Weinberg/PAS: hi-hat above the staff, ride on the top line) | `notation: pas` |
| `source-kind` | where the notes come from: `audio` (transcribed from the recording), `research` (lessons, game charts, no listening) or `generated` (a practice groove, not a song) | `source-kind: audio` |
| `transcriber`, `source`, `notes` | printed in "About this chart" | |

## 2. Instrument rows and the grid

A row is an instrument code followed by the grid. **Beats are separated by
spaces; each character is one equal slice of that beat.** Bars are separated by `|`.

```
HH  x-x- x-x- x-x- x-x-       # 4/4, sixteenth grid (4 chars per beat): 8th-note hats
SN  ---- x--- ---- x---       # snare on 2 and 4
BD  x--- --x- x-x- ----       # kick on 1, &2, 3, &3
```

* Characters per beat set the subdivision **for that beat**: 1 = quarter,
  2 = 8ths, 3 = 8th-note triplet, 4 = 16ths, 6 = 16th-note sextuplet,
  8 = 32nds. Different beats in one bar may use different subdivisions
  (e.g. `x-x- x-x x-x- xxxxxx`).
* Rows of the same beat may use different resolutions only if one divides the
  other (`x-` and `x--x`): coarse rows are expanded. Triplet vs. 16ths in the
  same beat is an error — write every row of that beat at the same length.
* `-` or `.` = silence. Use whichever reads better.
* Write 16ths (`x-x-`) even for 8th-note grooves when a nearby beat needs 16ths:
  the engraver picks the simplest note values automatically (a lone hit on a
  triplet downbeat becomes a plain quarter, `x-x-` becomes two 8ths).

### Instrument codes (staff positions follow the user's Drum Key)

| code | instrument | staff (Drum Key) | voice | notes |
|---|---|---|---|---|
| `TB` | tambourine | C6, square | hands | rarely part of the kit |
| `CH` | china | B5, circled X | hands | |
| `SP` | splash | B5, hollow diamond | hands | |
| `CB` | cowbell | B5, filled triangle | hands | |
| `C2` | crash 2 | B5, X | hands | |
| `CR` | crash (1) | A5 (first ledger line), X | hands | `k` choked: X with a dot |
| `RD` | ride | G5 (space above the staff), X | hands | `b` bell (filled diamond) |
| `HH` | hi-hat (sticks) | F5 (top line), X | hands | `o` open (circled X), `h` half-open |
| `R2` | second ride | D5, X | hands | |
| `T1` | high tom | E5 | hands | |
| `T2` | mid tom | D5 | hands | |
| `SN` | snare | C5 | hands | `c` rim click / cross-stick (X), `r` rimshot |
| `T3` | low rack tom | B4 | hands | only for 3-rack-tom kits |
| `FT` | floor tom | A4 | hands | |
| `F2` | low floor tom | G4 | hands | |
| `BD` | bass drum (right foot) | F4 | feet | |
| `B2` | left bass drum | E4 | feet | for a real 2nd kick; double pedal stays `BD` |
| `HF` | hi-hat pedal | D4, X | feet | `o` = hi-hat splash (circled X) |
| `ST` | sticking row | — | — | letters `R` `L` `B` (both) |

With `notation: pas` the hi-hat moves to G5 and the ride to F5, china/splash/cowbell
use the PAS heads, and open hi-hats get an "o" above (the next closed one a "+").

Aliases are accepted (`SD`, `KD`, `K`, `HT`, `MT`, `LT`→floor tom, `RIDE`, `CRASH`...).

## 3. Characters (articulations)

| char | meaning | allowed on |
|---|---|---|
| `x` | normal hit | all |
| `X` | accented hit (>) | all |
| `g` | ghost note — parentheses | drums, hi-hat, ride |
| `f` / `F` | flam / accented flam | drums, hi-hat |
| `d` | drag (two grace notes) | drums, hi-hat |
| `z` | buzz roll (z on the stem; lasts until the next hit in the grid) | drums, hi-hat |
| `o` / `O` | open hi-hat / accented open hi-hat (circled X; with `notation: pas` an "o" above and "+" on the next closed hit) | `HH` |
| `h` | half-open hi-hat | `HH` |
| `o` | foot splash | `HF` |
| `b` / `B` | ride bell / accented bell | `RD`, `R2` |
| `c` | cross-stick (side-stick) | `SN` |
| `r` / `R` | rimshot / accented rimshot (only when the sound really changes) | `SN` |
| `k` | choked cymbal (grab it) | cymbals, ride |

## 4. Patterns

```
pattern verse                 # 1-bar pattern
  HH  x-x- x-x- x-x- x-x-
  SN  ---- x--- ---- x---
  BD  x--- --x- x--- ----

pattern verse-crash from verse  # copy of 'verse'; listed rows replace the copied ones
  CR  x--- ---- ---- ----
  HH  ---- x-x- x-x- x-x-

pattern riff                  # 2-bar pattern: separate bars with |
  HH  x-x- x-x- x-x- x-x- | x-x- x-x- x-x- x-xo
  SN  ---- x--- ---- x--- | ---- x--- ---- x---
  BD  x--- --x- x--- ---- | x--- --x- x-x- ----

pattern shuffle time 12/8     # a pattern can declare its meter
  RD  x-x x-x x-x x-x
  SN  --- x-- --- x--
  BD  x-- --x x-- ---
```

* Names are single words (`verse`, `chorus-a`, `fill-1`). Define each pattern
  before the first `play` that uses it.
* `from BASE` copies every row of BASE; any row you list **replaces** that
  instrument's row. To drop an instrument, give it an all-rest row.
* Make a separate pattern for every distinct bar. Variations get their own
  names (`verse-open`, `chorus-last`), so that a repeat sign always means
  "exactly the previous bar".

## 5. Sections and statements

```
section Chorus 1
  mark C                      # optional rehearsal letter (skip I)
  at 0:58                     # where the section starts in the recording
  confidence medium "fill in bar 8 approximated"
  note "Hi-hat is washy; half-open throughout"
  play chorus x7              # 7 bars of 'chorus'
  play fill-2                 # bar 8
```

| statement | effect |
|---|---|
| `play NAME [xN] [@dir ...]` | play a pattern N times; inline directives apply to its first bar |
| `bar` + indented rows | a one-off bar written inline (rows on the following lines) |
| `rest N ["text"]` | N bars tacet, drawn as one multi-bar rest. `rest N each "text"` draws N separate empty bars |
| `@directive ...` | applies to the **next** bar produced |
| `time 3/4`, `tempo 120` | same as `@time`, `@tempo` |
| `break` | start a new line before the next bar |
| `at`, `mark`, `confidence`, `note`, `per-line` | section metadata |

Every section starts on a new line. The renderer turns a bar identical to the
one before it into a one-bar repeat sign (and two-bar patterns into two-bar
repeat signs), numbering each with its position in the section. The colour
grid still shows the hits faintly, so nothing is hidden.

## 6. Directives

| directive | meaning |
|---|---|
| `@dyn mf [beat=3]` | dynamic (pp p mp mf f ff fff sfz) |
| `@cresc [bars=N]` / `@dim [bars=N]` | hairpin over this bar (or N bars on the same line) |
| `@text "Vocals in"` | cue or instruction in italics (`@cue` is the same) |
| `@fill` | marks a fill bar with the word "Fill" |
| `@stop` | "Stop" (write the rests in the bar too) |
| `@tempo 140 ["label"]` | new tempo; `@tempo 70 q. Half-time` |
| `@rit` / `@accel` / `@atempo` | gradual tempo change text |
| `@time 7/8 2+2+3` | new time signature from this bar on |
| `@fermata [beat]` | fermata over a beat (default 1) |
| `@confidence low|medium "why"` | marks this bar as uncertain (dashed outline + note) |
| `@nosimile` | always write this bar out, even if it repeats the previous one |
| `@break` | start a new line at this bar |

## 7. Meters, tuplets and counting

* Simple meters (`2/4 3/4 4/4 5/4 2/2`): one group per beat.
* Compound meters (`6/8 9/8 12/8`): one group per dotted quarter, so `x-x` is
  a quarter + 8th (the shuffle) and `xxx` is three 8ths.
* Odd meters need a grouping: `7/8 2+2+3`, `5/8 3+2`. Write one space-separated
  group per grouping unit (in 8ths).
* Counts printed under the staff: `1 e & a`, `1 &`, `1 trip let`,
  `1 la li & la li`; 6/8 counts eighths `1 2 3 4 5 6`; 12/8 counts `1 & a 2 & a ...`.
* Swing/shuffle: if the song is a triplet shuffle in 4/4, either write it
  in 12/8 or write triplets (`x-x`) in 4/4; say which in `feel:`.

## 8. Worked example

```
title: Example Rock Song
artist: The Examples
tempo: 94
time: 4/4
feel: Straight 8ths
length: 3:30
source-kind: generated

pattern main
  HH  x-x- x-x- x-x- x-x-
  SN  ---- x--- ---- x---
  BD  x--- ---- x-x- ----

pattern main-crash from main
  CR  x--- ---- ---- ----
  HH  ---- x-x- x-x- x-x-

pattern fill-a
  HH  x-x- x-x- ---- ----
  SN  ---- x--- xxxx xx--
  FT  ---- ---- ---- --xx
  BD  x--- ---- x--- ----

section Intro
  at 0:00
  @text "Hi-hat count-in, guitar riff"
  play main-crash
  play main x6
  play fill-a @fill
```

## 9. Validation errors

`drum-agent check song.drums` stops at the first problem with a line number:

* `row has 3 beat group(s) but 4/4 needs 4` → missing or extra space between beats.
* `beat 2 mixes incompatible subdivisions ([3, 4])` → a triplet row and a 16th row in the same beat; rewrite with the same length.
* `'o' is not valid for Snare` → wrong character for the instrument (see §3).
* `unknown pattern 'verse2'` → define it first, check spelling.
* `pattern 'x' is in 6/8 but the current time is 4/4` → add `@time 6/8` before it.
* The summary's **timing check** lists sections whose computed start time drifts
  more than 4 s from their `at` timestamp: usually a wrong bar count or tempo.
