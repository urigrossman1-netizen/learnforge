---
name: drum-groove
description: Write, explain and play practice drum material that is not a transcription of a specific recording - beats in a style ("a funk groove with ghost notes", "a 6/8 ballad beat", "a trap beat"), fills, rudiment exercises with sticking (paradiddles, flam accents, rolls), coordination and reading exercises, or a practice chart that builds up a groove. Renders them as the same zoomable chart pages with real drum sounds. Use when the user asks for a beat, groove, fill, rudiment, drum exercise or lesson, or how to play or count a drum figure. For the drums of a particular song, use the drum-chart skill instead.
---

# Drum grooves and exercises

You write practice charts a drum teacher would hand out: correct, playable,
clearly counted, labelled as practice material. Same `.drums` format, renderer
and real-drum playback as the drum-chart skill.

## Toolkit and references
Run `drum-agent <command>` (on PATH with the plugin; otherwise
`${CLAUDE_SKILL_DIR}/../../../bin/drum-agent`, or clone
https://github.com/urigrossman1-netizen/drum-agent and use its `bin/drum-agent`).
The references live with the drum-chart skill: `drum-agent root` prints the
toolkit folder, and the files are in `.claude/skills/drum-chart/references/`:
- `format.md`: the chart format (**read before writing**),
- `grooves.md`: correctly notated grooves by style, fills and endings, with typical tempos,
- `rudiments.md`: the 40 PAS rudiments and written-out exercises with sticking,
- `notation.md`: how to notate well.

## Workflow
1. Pick the material: start from the closest pattern in `grooves.md` or
   `rudiments.md` and adapt it to the request (tempo, feel, difficulty). Do not
   claim a groove is "the" beat of a particular song; if the user names a song,
   offer the drum-chart skill, which listens to the recording.
2. Write `<name>.drums` with:
   - `source-kind: generated` and a transcriber line such as
     "Practice groove by drum-agent: a typical <style> beat, not a transcription";
   - a tempo in the style's usual range, `feel:`, a section per step
     (e.g. "Groove", "Variation", "Fill", "Groove + fill"), repeats as `play name x4`;
   - sticking (`ST` row) for fills and rudiments; accents `X`, ghosts `g`, flams `f`;
   - a short `note` per section on what to listen for and how to count it.
   For a build-up lesson, go from simple to full: hands only, add kick, add ghosts.
3. `drum-agent check name.drums`: fix every error and every `playability:` warning
   (three hands at once, left-foot conflicts, an open hat while the pedal closes,
   sticking with no hand note).
4. `drum-agent render name.drums --midi name.mid` (and `--pdf` to print). Give
   the user the page: they can zoom, play it with real drums, slow it down, loop
   it, turn the click on. Explain in two or three sentences how to count it and
   the one thing to watch.

## Good practice charts
- One idea per section; 4 or 8 bars each; end with something that loops back.
- Count it out loud in the notes ("1 e & a 2 e & a"; "1 & a 2 & a" in 12/8).
- Tempos: give a slow practice tempo and the target style tempo.
- Ghost notes very soft, accents clearly louder; say so.
