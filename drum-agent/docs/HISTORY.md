# How this drum agent came together

The drum agent was built across several Claude chats in the user's "Drum agent"
project. None of those chats pushed their work to GitHub, so it was recovered
from the session transcripts in October 2026 and consolidated here, in one
repository, as the user asked: "Make another repo, especially for the Drum agent
thing. Where all the drum skills and things that relates to the drum agent go
there."

| Chat | What it built | What lives on here |
|---|---|---|
| **Senior architect role setup** (Sep 27) | The master spec: one coherent pipeline from song to editable, exportable chart; no fabricated notes; measure accuracy; the P0-P12 priority order. User decisions: local single user, Claude optional, a swappable drum separator. | `docs/REQUIREMENTS.md` follows that spec. |
| **YouTube/Spotify MCP integration** (Oct 7-8, this repo's starting point) | The `drum_agent` package: Spotify metadata, YouTube search and download with yt-dlp, ffmpeg, the signal-processing transcriber (kick, snare, hi-hat, crash; tempo, downbeats, grooves, sections, fills), MIDI, `setup` and `doctor`, the two MCP servers, the MDB Drums evaluation. | `src/drum_agent/` (acquisition, `transcribe.py`, `pipeline.py`, `doctor.py`, `mcp.py`), `eval/`. |
| **Drum chart readability and zoom** (Oct 5-7) | The `.drums` chart format and engraver: engraved staff with Bravura glyphs, count row, colour hit grid, zoom that reflows 4/2/1 bars per line, dark mode, print, playback; the drum-charts skill and its references; the rhythm-game chart reader; charts for Burnout, Smells Like Teen Spirit and Lithium (published as the user's private artifacts). | `src/drum_agent/drumchart/` (re-renders the three published charts byte for byte), `gamechart.py`, the skill references. The three song charts stay private (artifacts), not in this public repo. |
| **Drum agent repository usage** (Oct 6) | A browser drum agent following the user's own **Drum Key** picture, a recorded acoustic kit (Hydrogen GMRockKit) instead of synthesized sounds, a playability validator, a knowledge base of style grooves, rudiment exercises and the 40 PAS rudiments. | The Drum Key is the default notation; the GMRockKit samples play every chart; `playability.py`; the style and rudiment library in the references; the `drum-groove` skill. |
| **Drum Agent transcription pipeline** (Oct 6-7) | A rigorous core design: raw vs quantized timing, confidence that is measured not invented, logged cleanup, mandatory provenance (transcribed vs generated), audio validation, job records; ADTOF measured on MDB Drums. | Provenance (`source-kind`), plain-language input checks, `job.json` records; its measurements informed the listening work. |

The user's own words that shaped it:
- "Make them easy to read and make them look really good ... so that you can also zoom into the charts."
- "the drum charts are supposed to be like the picture" (the Drum Key).
- "All the sounds are supposed to be from real sounds, like a snare, a bass drum."
- "You search the song, download the MP3 or WAV, and listen to it really well, and then find all the drum charts."
- "DO NOT tell me the system is accurate merely because it executes successfully."
- "Every time I build something that is related to the drum agent I can use that thing" (hence the Claude Code plugin).
