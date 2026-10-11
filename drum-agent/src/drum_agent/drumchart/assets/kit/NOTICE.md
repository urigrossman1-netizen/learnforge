# Drum samples: source and license

The MP3 files in this folder are **real recordings** of a 5-piece Pearl DX drum kit from the
Hydrogen drum kit **GMRockKit**.

- Authors: Glen MacArthur / Sebastian Moors
- Source: https://github.com/hydrogen-music/hydrogen/tree/master/data/drumkits/GMRockKit
- License: GNU General Public License v3 or later (https://www.gnu.org/licenses/gpl-3.0.html).
  This license applies to these sample files only, not to the rest of drum-agent.

Changes: three velocity layers per instrument were selected, the silent tail after -60 dB was
trimmed with a 20 ms fade, and the result was encoded as mono 96 kbps MP3.
`tools/build_kit.py` is the complete recipe; `kit.json` lists which original file each layer
came from.

Chart pages embed the samples they need for playback, so a chart page you share carries
these GPL-licensed recordings: keep this attribution with it.
