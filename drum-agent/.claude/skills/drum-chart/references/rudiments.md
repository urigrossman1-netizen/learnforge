# Rudiments and practice exercises

The 40 PAS International Drum Rudiments, and written-out exercises (with sticking)
for the most useful ones. Sticking goes in an `ST` row: `R`, `L`, `B` (both).
Accents are `X`, flams `f`, drags `d`, buzz strokes `z`. Every block parses
(tested by `tests/test_drumchart.py`).

## The 40 PAS rudiments

- **Roll rudiments:** single stroke roll, single stroke four, single stroke seven,
  multiple bounce roll, triple stroke roll, double stroke open roll, five / six / seven /
  nine / ten / eleven / thirteen / fifteen / seventeen stroke rolls.
- **Diddle rudiments:** single, double and triple paradiddle, single paradiddle-diddle.
- **Flam rudiments:** flam, flam accent, flam tap, flamacue, flam paradiddle, single
  flammed mill, flam paradiddle-diddle, pataflafla, Swiss army triplet, inverted flam
  tap, flam drag.
- **Drag rudiments:** drag (ruff), single drag tap, double drag tap, lesson 25, single
  dragadiddle, drag paradiddle #1 and #2, single, double and triple ratamacue.

## Exercises

```
# Single stroke roll (16ths)
pattern single-stroke
  SN  xxxx xxxx xxxx xxxx
  ST  RLRL RLRL RLRL RLRL

# Double stroke open roll (16ths)
pattern double-stroke
  SN  xxxx xxxx xxxx xxxx
  ST  RRLL RRLL RRLL RRLL

# Single paradiddle, accent on each first note, kick on the beat
pattern paradiddle
  SN  Xxxx Xxxx Xxxx Xxxx
  BD  x--- x--- x--- x---
  ST  RLRR LRLL RLRR LRLL

# Double paradiddle in 12/8
pattern double-paradiddle time 12/8
  SN  Xxx xxx Xxx xxx
  ST  RLR LRR LRL RLL

# Triple paradiddle (16ths)
pattern triple-paradiddle
  SN  Xxxx xxxx Xxxx xxxx
  ST  RLRL RLRR LRLR LRLL

# Single paradiddle-diddle in 12/8
pattern paradiddle-diddle time 12/8
  SN  Xxx xxx Xxx xxx
  ST  RLR RLL LRL LRR

# Flam accent (8th-note triplets)
pattern flam-accent
  SN  Fxx Fxx Fxx Fxx
  ST  RLR LRL RLR LRL

# Five stroke roll: two doubles and an accent, on the 8th-note grid
pattern five-stroke
  SN  xxxx X--- xxxx X---
  ST  RRLL R--- LLRR L---

# Drag tap (ruff on the beat)
pattern drag-tap
  SN  d-x- d-x- d-x- d-x-
  ST  R-L- L-R- R-L- L-R-

# Buzz roll, quarter-note pulses
pattern buzz-roll
  SN  z--- z--- z--- X---
```

## Practice tips to give the player
- Start at a tempo you can play perfectly (often 60-70 BPM), with the click on.
- Keep the accents loud and the other notes low (about 2 inches from the head).
- When it is clean four times in a row, add 5 BPM.
