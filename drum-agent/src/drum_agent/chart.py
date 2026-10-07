"""Render a transcription as a Markdown drum-chart draft and a General MIDI file."""

from __future__ import annotations

from pathlib import Path

from .transcribe import GM_NOTES

ROWS = (("CR", "crash", "x"), ("HH", "hihat", "x"), ("SN", "snare", "o"), ("BD", "kick", "o"))
COUNTS = {4: ["", "e", "&", "a"], 3: ["", "&", "a"], 2: ["", "&"], 1: [""]}


def counting(bpb: int, sub: int) -> str:
    """Count line with exactly one character per grid step, so it lines up with the tab."""
    syll = COUNTS.get(sub, ["", *["."] * (sub - 1)])
    return " ".join(str(b + 1)[-1] if i == 0 else syll[i] for b in range(bpb) for i in range(sub))


def meter(bpb: int, sub: int) -> str:
    """Time signature: a triplet grid (3 steps per beat) is compound time (6/8, 12/8)."""
    return f"{bpb * 3}/8" if sub == 3 else f"{bpb}/4"


def _cell(text) -> str:
    """Make text safe inside a Markdown table cell."""
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def tab(hits: dict, bpb: int, sub: int, *, dynamics: bool = False) -> str:
    """ASCII drum tab. `hits` maps instrument -> steps, or -> [step, velocity] pairs.

    With dynamics: X/O = accent, g = ghost snare.
    """
    steps = bpb * sub
    lines = ["     " + counting(bpb, sub)]
    for label, name, mark in ROWS:
        cells = ["."] * steps
        for h in hits.get(name, []):
            st, vel = (h, None) if isinstance(h, int) else (h[0], h[1])
            if not 0 <= st < steps:
                continue
            sym = mark
            if dynamics and vel is not None:  # a typical hit has velocity 0.7
                if vel >= 0.95:
                    sym = mark.upper()
                elif name == "snare" and vel < 0.35:
                    sym = "g"
            cells[st] = sym
        if name == "crash" and not hits.get(name):
            continue
        lines.append(f"{label} | " + " ".join(cells) + " |")
    return "\n".join(lines)


def _clock(t: float) -> str:
    minutes, seconds = divmod(round(max(0.0, t), 1), 60)
    return f"{int(minutes)}:{seconds:04.1f}"


def markdown(result: dict, meta: dict | None = None) -> str:
    meta = meta or {}
    tempo = result["tempo"]
    bpb, sub = tempo["beats_per_bar"], tempo["subdivision"]
    sp, yt = meta.get("spotify") or {}, meta.get("youtube") or {}
    title = meta.get("title") or sp.get("title") or yt.get("title") or "Untitled"
    artist = meta.get("artist") or ", ".join(sp.get("artists") or []) or ""
    bars = result["bars"]

    out = [f"# Drum chart (draft): {title}" + (f" — {artist}" if artist else ""), ""]
    out.append("> Machine transcription by drum-agent. Verify by ear before you rely on it.")
    out += ["", "| | |", "|---|---|"]
    out.append(f"| Tempo | ♩ ≈ {tempo['bpm']:g} BPM (range {tempo['bpm_min']:g}–{tempo['bpm_max']:g}) |")
    assumed = bpb == 4 and sub == 4
    out.append(f"| Time | {meter(bpb, sub)} ({'assumed' if assumed else 'set by user'}) |")
    out.append(f"| Length | {_clock(result['duration_s'])}, {len(bars)} bars |")
    if tempo.get("first_downbeat_s") is not None:
        out.append(f"| Bar 1 starts | {_clock(tempo['first_downbeat_s'])} |")
    if sp.get("url"):
        out.append(
            f"| Spotify | [{_cell(sp.get('title'))}]({_cell(sp['url'])}) · {_cell(sp.get('album'))} "
            f"({_cell(sp.get('release_date'))}) |"
        )
    if yt.get("url"):
        out.append(f"| Audio source | [{_cell(yt.get('title') or yt['url'])}]({_cell(yt['url'])}) |")
    elif meta.get("audio_file"):
        out.append(f"| Audio source | {_cell(meta['audio_file'])} |")

    out += ["", "## Road map", "", "| # | Label | Bars | Starts | Length | Groove | Level | Crashes | Fills |",
            "|---|---|---|---|---|---|---|---|---|"]
    for s in result["sections"]:
        crashes = ", ".join(map(str, s["crash_bars"])) or "—"
        fills = ", ".join(map(str, s.get("fills", []))) or "—"
        out.append(
            f"| {s['index']} | {s['label']} | {s['first_bar']}–{s['last_bar']} | {_clock(s['start_s'])} | "
            f"{s['bars']} | {s['groove'] or '—'} | {s['energy_db']:g} dB | {crashes} | {fills} |"
        )

    out += ["", "## Grooves", ""]
    for name, g in result["grooves"].items():
        if g["bars"] < 2 and len(result["grooves"]) > 3:
            continue  # one-off bars are listed under fills/variations
        sections = sorted({bars[i - 1].get("section") for i in g["bar_indices"]} - {None})
        out.append(f"### Groove {name} — {g['bars']} bar(s), sections {', '.join(map(str, sections))}")
        out += ["", "```text", tab(g["pattern"], bpb, sub), "```", ""]

    variations = [b for b in bars if b.get("fill") or (b["groove"] and result["grooves"][b["groove"]]["bars"] < 2)]
    if variations:
        out += ["## Fills and variations", ""]
        for b in variations:
            kind = "Fill" if b.get("fill") else "Variation"
            out.append(f"### {kind}: bar {b['index']} ({_clock(b['start_s'])}), section {b.get('section')}")
            out += ["", "```text", tab(b["hits"], bpb, sub, dynamics=True), "```", ""]

    inferred = [b["index"] for b in bars if b.get("inferred")]
    out += ["## Notes", ""]
    out += [f"- {n}" for n in result["notes"]]
    if inferred:
        out.append(f"- Hi-hats hidden under snare hits were filled in on bars {_ranges(inferred)}.")
    out.append("- Legend: x = cymbal, o = drum, X/O = accent, g = ghost note, . = rest.")
    out.append("- Section labels: same letter = similar groove and level. Name them (Verse, Chorus…) by ear.")
    return "\n".join(out) + "\n"


def _ranges(nums: list[int]) -> str:
    out, start = [], None
    for i, n in enumerate(nums):
        if start is None:
            start = n
        if i == len(nums) - 1 or nums[i + 1] != n + 1:
            out.append(str(start) if start == n else f"{start}–{n}")
            start = None
    return ", ".join(out)


def write_midi(result: dict, path: Path) -> Path:
    """Quantized GM drum track (channel 10) at the average tempo, bar 1 at tick 0.

    Ticks are computed exactly for any grid; a triplet grid is written as
    compound time (6/8, 12/8), with the dotted quarter as the beat.
    """
    import mido

    tempo = result["tempo"]
    bpb, sub = tempo["beats_per_bar"], tempo["subdivision"]
    tpb = 480
    compound = sub == 3
    beat_ticks = tpb * 3 // 2 if compound else tpb  # dotted quarter in compound time
    quarter_bpm = tempo["bpm"] * (1.5 if compound else 1.0)
    mid = mido.MidiFile(ticks_per_beat=tpb)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Drums", time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(quarter_bpm), time=0))
    num, den = (bpb * 3, 8) if compound else (bpb, 4)
    track.append(mido.MetaMessage("time_signature", numerator=num, denominator=den, time=0))
    events = []
    for k, bar in enumerate(result["bars"]):
        for name, hs in bar["hits"].items():
            for st, vel in hs:
                step = k * bpb * sub + st
                tick = round(step * beat_ticks / sub)
                off = round((step + 0.5) * beat_ticks / sub)
                v = int(max(1, min(127, 40 + 87 * vel)))
                events.append((tick, 1, GM_NOTES[name], v))
                events.append((off, 0, GM_NOTES[name], 0))
    now = 0
    for tick, on, note, vel in sorted(events):
        kind = "note_on" if on else "note_off"
        track.append(mido.Message(kind, channel=9, note=note, velocity=vel, time=tick - now))
        now = tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(path))
    return path
