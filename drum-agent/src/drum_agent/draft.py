"""Turn an automatic transcription (analysis.json) into a draft .drums chart.

The draft is a faithful rewrite of what the analysis detected: one pattern per
distinct bar (identical consecutive bars become `play name xN`, which the
engraver shows as repeat signs), sections with neutral names (Part A, Part B,
Part A 2 ...: same letter = same-sounding material), fills marked, and every
bar the analysis is unsure about flagged with `@confidence` and the reason.
Nothing is added that the analysis did not detect. Claude (or the user) then
reviews the draft against the recording and saves the final chart.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

# analysis drum name -> (.drums instrument code, row order in the draft)
INSTRUMENT_CODES = {"crash": "CR", "hihat": "HH", "snare": "SN", "kick": "BD"}
ROW_ORDER = ("CR", "HH", "SN", "BD")
ACCENT_VELOCITY = 0.95  # analysis velocities: a typical hit is about 0.7
GHOST_VELOCITY = 0.35   # a snare below this is written as a ghost note


def meter_text(beats_per_bar: int, subdivision: int) -> str:
    """The .drums time signature for the analysis grid (compound when the beat splits in 3)."""
    return f"{beats_per_bar * 3}/8" if subdivision == 3 else f"{beats_per_bar}/4"


def tempo_text(bpm: float, subdivision: int) -> str:
    """Analysis tempo is beats per minute; in compound meters the beat is a dotted quarter."""
    return f"{round(bpm)} q." if subdivision == 3 else f"{round(bpm)}"


def _clock(seconds: float) -> str:
    minutes, secs = divmod(round(max(0.0, seconds), 1), 60)
    return f"{int(minutes)}:{secs:04.1f}"


def _char(drum: str, velocity: float) -> str:
    """Only the snare's loudness is reliable enough in a mix to write accents and ghost notes."""
    if drum != "snare":
        return "x"
    if velocity < GHOST_VELOCITY:
        return "g"
    return "X" if velocity >= ACCENT_VELOCITY else "x"


def bar_rows(bar: dict, beats: int, subdivision: int, first_beat: int = 1) -> dict[str, str]:
    """Grid rows of one analysis bar: {code: 'x-x- x-x- ...'}; beats = beats actually in the bar."""
    offset = (first_beat - 1) * subdivision
    rows = {}
    for drum, code in INSTRUMENT_CODES.items():
        cells = ["-"] * (beats * subdivision)
        for step, velocity in bar["hits"].get(drum, []):
            k = step - offset
            if 0 <= k < len(cells):
                cells[k] = _char(drum, velocity)
        if any(c != "-" for c in cells):
            rows[code] = " ".join("".join(cells[b * subdivision : (b + 1) * subdivision]) for b in range(beats))
    return rows


def _bar_shape(bar: dict, bpb: int) -> tuple[int, int]:
    """(first beat, number of beats) of a bar; partial bars keep only their real beats."""
    partial = bar.get("partial")
    if partial:
        return int(partial["first_beat"]), int(partial["beats"])
    return 1, bpb


def _flags(bar: dict, bpb: int, sub: int) -> list[str]:
    """Why this bar deserves a second listen (empty = nothing special)."""
    reasons = []
    if bar.get("partial"):
        reasons.append("incomplete bar where the count restarts (stop, pickup or tempo change)")
    if bar.get("fill"):
        reasons.append("fill: toms are heard as snare or kick, check by ear")
    return reasons


def draft_chart(result: dict, meta: dict, audio_name: str | None = None) -> str:
    """The .drums text for an analysis result. meta: title/artist/album/... (any may be missing)."""
    t = result["tempo"]
    bpb, sub = int(t["beats_per_bar"]), int(t["subdivision"])
    bars = result["bars"]
    meter = meter_text(bpb, sub)
    sp = meta.get("spotify") or {}
    title = meta.get("title") or sp.get("title") or (Path(audio_name).stem if audio_name else "Untitled")
    artist = meta.get("artist") or ", ".join(sp.get("artists") or []) or ""
    album = sp.get("album")
    year = (sp.get("release_date") or "")[:4]
    duration = float(result.get("duration_s") or 0)

    head = [f"title: {title}"]
    if artist:
        head.append(f"artist: {artist}")
    if album:
        head.append(f"album: {album}{f' ({year})' if year else ''}")
    head += [
        f"tempo: {tempo_text(t['bpm'], sub)}",
        f"time: {meter}",
        f"length: {int(duration // 60)}:{int(duration % 60):02d}",
        "source-kind: audio",
        "transcriber: drum-agent automatic transcription (draft: check every bar by ear before trusting it)",
        f"source: Detected from {audio_name or 'the recording'} on {date.today().isoformat()}: "
        f"tempo {t['bpm']} BPM (range {t.get('bpm_min')}-{t.get('bpm_max')}), "
        f"{len(bars)} bars, instruments the analysis can hear: kick, snare, hi-hat/ride, crash.",
        "notes: " + " ".join(result.get("notes") or []),
        "",
    ]

    patterns: dict[tuple, str] = {}
    pattern_lines: list[str] = []
    counters: dict[str, int] = {}

    def pattern_for(rows: dict[str, str], bar_meter: str, base: str) -> str | None:
        if not rows:
            return None
        key = (bar_meter, tuple(sorted(rows.items())))
        if key in patterns:
            return patterns[key]
        counters[base] = counters.get(base, 0) + 1
        name = base if counters[base] == 1 else f"{base}-{counters[base]}"
        patterns[key] = name
        pattern_lines.append(f"pattern {name}" + (f" time {bar_meter}" if bar_meter != meter else ""))
        for code in ROW_ORDER:
            if code in rows:
                pattern_lines.append(f"  {code:<3} {rows[code]}")
        pattern_lines.append("")
        return name

    if not bars:
        raise ValueError("The analysis found no drum hits, so there is nothing to chart.")
    sections = result.get("sections") or [
        {"index": 1, "first_bar": bars[0]["index"], "last_bar": bars[-1]["index"], "label": "A"}
    ]
    song_bpm = round(float(t["bpm"]))
    seen: dict[str, int] = {}
    body: list[str] = []
    current_meter, current_bpm = meter, song_bpm
    for sec in sections:
        label = sec.get("label") or "A"
        seen[label] = seen.get(label, 0) + 1
        sec_bars = [b for b in bars if sec["first_bar"] <= b["index"] <= sec["last_bar"]]
        if not sec_bars:
            continue
        body.append(f"section Part {label}" + (f" {seen[label]}" if seen[label] > 1 else ""))
        body.append(f"  at {_clock(sec_bars[0]['start_s'])}")
        if seen[label] > 1:
            body.append(f'  note "Sounds like Part {label}"')
        restored = sum(1 for b in sec_bars if (b.get("inferred") or {}).get("hihat"))
        if restored:
            body.append(f'  note "Hi-hat strokes under the snare are inferred in {restored} bar(s): the snare hides them"')
        bpm = _section_bpm(sec_bars, bpb) or song_bpm
        if abs(bpm - current_bpm) >= 3:  # keeps the chart's clock and playback with the recording
            body.append(f"  tempo {tempo_text(bpm, sub)}")
            current_bpm = bpm
        run: list = []  # [pattern name or None for an empty bar, count]

        def flush():
            if run:
                nm, n = run
                body.append(f"  rest {n}" if nm is None else f"  play {nm}" + (f" x{n}" if n > 1 else ""))
                run.clear()

        for bar in sec_bars:
            first_beat, beats = _bar_shape(bar, bpb)
            bar_meter = meter if beats == bpb else (f"{beats * 3}/8" if sub == 3 else f"{beats}/4")
            base = "fill" if bar.get("fill") else "groove-" + (bar.get("groove") or "x").lower()
            nm = pattern_for(bar_rows(bar, beats, sub, first_beat), bar_meter, base)
            directives = (["@fill"] if bar.get("fill") else []) + [
                '@confidence medium "' + "; ".join(r).replace('"', "'") + '"' for r in [_flags(bar, bpb, sub)] if r
            ]
            if bar_meter != current_meter:
                flush()
                body.append(f"  @time {bar_meter}")
                current_meter = bar_meter
            if directives:  # a marked bar stands alone so its mark lands on that bar
                flush()
                if nm is None:
                    body.extend(f"  {d}" for d in directives)
                    body.append("  rest 1")
                else:
                    body.append(f"  play {nm} {' '.join(directives)}")
            elif run and run[0] == nm:
                run[1] += 1
            else:
                flush()
                run[:] = [nm, 1]
        flush()
        body.append("")
    return "\n".join(head + pattern_lines + body).rstrip() + "\n"


def _section_bpm(sec_bars: list[dict], bpb: int) -> int | None:
    """Median tempo of a section's complete bars (beats per minute)."""
    import statistics

    lengths = [b["end_s"] - b["start_s"] for b in sec_bars if not b.get("partial") and b["end_s"] > b["start_s"]]
    if not lengths:
        return None
    return round(60.0 * bpb / statistics.median(lengths))
