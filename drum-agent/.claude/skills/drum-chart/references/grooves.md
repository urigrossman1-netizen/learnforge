# Groove and fill library

Copy a pattern into your chart and **adapt it to the recording**: kick
placement, hi-hat openings, ghost notes and fills differ from song to song.
These are textbook versions. Every block below parses as-is (tested by
`tests/test_drumchart.py`).

## Contents
Rock & pop · Punk & hardcore · Grunge/alt textures · Funk & R&B ·
Shuffles & swing · Latin & reggae · Compound & odd meters · Fills · Endings

---

## Rock & pop

```
# Basic 8th-note rock: hats on 8ths, snare 2 & 4, kick 1 & 3
pattern rock
  HH  x-x- x-x- x-x- x-x-
  SN  ---- x--- ---- x---
  BD  x--- ---- x--- ----

# Rock with the "& of 3" kick (very common)
pattern rock-and3
  HH  x-x- x-x- x-x- x-x-
  SN  ---- x--- ---- x---
  BD  x--- ---- x-x- ----

# Rock with the "a of 2" pickup kick (Back in Black style)
pattern rock-a2
  HH  x-x- x-x- x-x- x-x-
  SN  ---- x--- ---- x---
  BD  x--- ---x x--- ----

# Same groove on the ride with the hi-hat foot on 2 & 4
pattern rock-ride
  RD  x-x- x-x- x-x- x-x-
  SN  ---- x--- ---- x---
  BD  x--- ---- x-x- ----
  HF  ---- x--- ---- x---

# Driving quarter-note crash/ride (big choruses)
pattern rock-quarters-crash
  CR  x--- x--- x--- x---
  SN  ---- x--- ---- x---
  BD  x--- ---- x-x- ----

# 16th hi-hats, one hand (ballads, pop)
pattern rock-16ths
  HH  xxxx xxxx xxxx xxxx
  SN  ---- x--- ---- x---
  BD  x--- --x- x--- ----

# Half-time feel: snare on 3
pattern half-time
  HH  x-x- x-x- x-x- x-x-
  SN  ---- ---- x--- ----
  BD  x--- ---x --x- ----

# Disco / four-on-the-floor with open hats on the "&"
pattern disco
  HH  x-o- x-o- x-o- x-o-
  SN  ---- x--- ---- x---
  BD  x--- x--- x--- x---
  HF  --x- --x- --x- --x-

# Motown: snare on every beat, tambourine on 2 & 4
pattern motown
  SN  x--- x--- x--- x---
  TB  ---- x--- ---- x---
  BD  x--- --x- x--- --x-
```

## Punk & hardcore

```
# Skank / two-step ("polka") beat: kick on the beat, snare on the &
pattern skank
  HH  x-x- x-x- x-x- x-x-
  SN  --x- --x- --x- --x-
  BD  x--- x--- x--- x---

# Fast punk 8ths with crash-ride on quarters (open, washy)
pattern punk-drive
  CR  x--- x--- x--- x---
  SN  ---- x--- ---- x---
  BD  x--- --x- x--- --x-

# Punk 8th-note "dance" beat: kick on every beat
pattern punk-dance
  HH  x-x- x-x- x-x- x-x-
  SN  ---- x--- ---- x---
  BD  x--- x--- x--- x---

# Blast beat (alternating 16ths)
pattern blast
  CR  x-x- x-x- x-x- x-x-
  SN  -x-x -x-x -x-x -x-x
  BD  x-x- x-x- x-x- x-x-
```

## Grunge / alternative textures

```
# Washy half-open hats, big backbeat
pattern washy-rock
  HH  h-h- h-h- h-h- h-h-
  SN  ---- X--- ---- X---
  BD  x--- --x- x-x- ----

# Floor-tom groove instead of hats (verse tension)
pattern floor-groove
  FT  x-x- x-x- x-x- x-x-
  SN  ---- x--- ---- x---
  BD  x--- --x- x--- ----

# Quiet verse: cross-stick on 2 & 4, hats closed
pattern cross-stick-verse
  HH  x-x- x-x- x-x- x-x-
  SN  ---- c--- ---- c---
  BD  x--- --x- x--- ----
```

## Funk & R&B

```
# 16th funk groove with ghost notes and an open hat
pattern funk-ghosts
  HH  x-x- x-x- x-x- x-xo
  SN  --g- X-gg -g-g X--g
  BD  x--- --x- --x- ----

# Linear funk (no two limbs together)
pattern linear
  HH  x--- --x- ---- x---
  SN  --g- X--g -gX- --g-
  BD  -x-- -x-- x--x -x--
  ST  RLR- RL-R LRR- RLRL
```

## Shuffles & swing

```
# 12/8 shuffle on the ride
pattern shuffle time 12/8
  RD  x-x x-x x-x x-x
  SN  --- x-- --- x--
  BD  x-- --x x-- ---

# Triplet shuffle written in 4/4 (quarter-8th triplets)
pattern shuffle-44
  HH  x-x x-x x-x x-x
  SN  --- x-- --- x--
  BD  x-- --- x-- ---

# Jazz ride pattern with hi-hat foot on 2 & 4
pattern swing time 4/4
  RD  x-- x-x x-- x-x
  HF  --- x-- --- x--
```

## Latin & reggae

```
# Reggae one drop: kick + cross-stick on 3
pattern one-drop
  HH  x-x x-x x-x x-x
  SN  --- --- c-- ---
  BD  --- --- x-- ---

# Bossa nova: cross-stick clave over a samba kick
pattern bossa
  HH  x-x- x-x- x-x- x-x-
  SN  c--c ---- c--- c---
  BD  x--x x--x x--x x--x

# Train beat: snare 16ths, accents on 2 & 4
pattern train
  SN  gggg Xggg gggg Xggg
  BD  x--- ---- x--- ----
```

## Compound & odd meters

```
# 6/8 ballad
pattern ballad-68 time 6/8
  HH  x-x-x- x-x-x-
  SN  ------ x-----
  BD  x----- ---x--

# 7/8 rock (2+2+3)
pattern seven-eight time 7/8 2+2+3
  HH  x-x- x-x- x-x-x-
  SN  ---- x--- ------
  BD  x--- ---- x-----

# 5/4 (3+2 feel)
pattern five-four time 5/4
  HH  x-x- x-x- x-x- x-x- x-x-
  SN  ---- ---- x--- ---- x---
  BD  x--- --x- ---- x--- ----
```

## Fills

```
# 1-beat snare fill into the next bar (beat 4)
pattern fill-1beat
  HH  x-x- x-x- x-x- ----
  SN  ---- x--- ---- xxxx
  BD  x--- ---- x--- ----

# 2-beat fill down the toms
pattern fill-toms
  HH  x-x- x-x- ---- ----
  SN  ---- x--- xx-- ----
  T1  ---- ---- --xx ----
  T2  ---- ---- ---- xx--
  FT  ---- ---- ---- --xx
  BD  x--- ---- ---- ----

# Full-bar 16th fill, snare to floor tom
pattern fill-bar
  SN  xxxx xx-- ---- ----
  T1  ---- --xx xx-- ----
  FT  ---- ---- --xx xxxx
  BD  x--- ---- x--- ----

# 8th-note triplet fill
pattern fill-triplets
  SN  xxx xxx --- ---
  T1  --- --- xxx ---
  FT  --- --- --- xxx
  BD  x-- --- x-- ---

# Bonham-style 16th-triplet tom/kick fill (hand-hand-foot)
pattern fill-bonham
  T1  x--x-- x--x-- ------ ------
  FT  ------ ------ x--x-- x--x--
  SN  -x--x- -x--x- -x--x- -x--x-
  BD  --x--x --x--x --x--x --x--x

# Flam accents on the snare, crash landing next bar
pattern fill-flams
  HH  x-x- x-x- ---- ----
  SN  ---- x--- F-F- F-FF
  BD  x--- ---- ---- ----

# Section landing: crash + kick on 1
pattern crash-1 from rock
  CR  x--- ---- ---- ----
  HH  ---- x-x- x-x- x-x-
```

## Endings

```
# Final hit, held
pattern final-hit
  CR  x--- ---- ---- ----
  SN  x--- ---- ---- ----
  BD  x--- ---- ---- ----

# Choked stop on beat 1 (band stops dead)
pattern choke-stop
  CR  k--- ---- ---- ----
  SN  X--- ---- ---- ----
  BD  x--- ---- ---- ----
```
