"""General MIDI of the detected performance, timed like the recording.

Every bar starts where it starts in the audio (a tempo change at each bar
follows the drummer's tempo), hits sit on the analysis grid inside the bar,
and partial bars (pickups, stops) keep their real number of beats. Bar 1 is
at tick 0. This is the MIDI to line up against the song in a DAW; the chart's
own MIDI (drum-agent render --midi) follows the written chart instead.
"""

from __future__ import annotations

from pathlib import Path

GM_NOTES = {"kick": 36, "snare": 38, "hihat": 42, "crash": 49}


def write_midi(result: dict, path: Path) -> Path:
    import mido

    tempo = result["tempo"]
    bpb, sub = tempo["beats_per_bar"], tempo["subdivision"]
    tpb = 480
    compound = sub == 3
    beat_ticks = tpb * 3 // 2 if compound else tpb  # the beat is a dotted quarter in compound time
    beat_ratio = 1.5 if compound else 1.0            # MIDI tempo counts quarter notes

    def signature(beats):
        num, den = (beats * 3, 8) if compound else (beats, 4)
        return mido.MetaMessage("time_signature", numerator=num, denominator=den)

    mid = mido.MidiFile(ticks_per_beat=tpb)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Drums (performance)", time=0))
    events = []  # (tick, order, message): meta before note-off before note-on
    bars = result["bars"]
    beat_pos, current_sig, current_tempo = 0, None, None
    for i, bar in enumerate(bars):
        part = bar.get("partial") or {}
        first, beats = part.get("first_beat", 1), part.get("beats", bpb)
        if beats != current_sig:
            events.append((round(beat_pos * beat_ticks), 0, signature(beats)))
            current_sig = beats
        if "start_s" in bar and "end_s" in bar:
            start = bar.get("grid_start_s", bar["start_s"]) + (first - 1) * _beat_seconds(bar, bpb)
            end = bars[i + 1]["start_s"] if i + 1 < len(bars) and "start_s" in bars[i + 1] else bar["end_s"]
            bpm = 60.0 * beats / max(1e-3, end - start) * beat_ratio
        else:  # no bar timing: the average tempo
            bpm = tempo["bpm"] * beat_ratio
        micro = mido.bpm2tempo(min(max(bpm, 20.0), 400.0))
        if micro != current_tempo:
            events.append((round(beat_pos * beat_ticks), 0, mido.MetaMessage("set_tempo", tempo=micro)))
            current_tempo = micro
        for name, hs in bar["hits"].items():
            for st, vel in hs:
                beat = beat_pos + st / sub - (first - 1)
                tick = round(beat * beat_ticks)
                off = round((beat + 0.5 / sub) * beat_ticks)
                v = int(max(1, min(127, 40 + 87 * vel)))
                events.append((tick, 2, mido.Message("note_on", channel=9, note=GM_NOTES[name], velocity=v)))
                events.append((off, 1, mido.Message("note_off", channel=9, note=GM_NOTES[name], velocity=0)))
        beat_pos += beats
    now = 0
    for tick, _, msg in sorted(events, key=lambda e: (e[0], e[1])):
        track.append(msg.copy(time=tick - now))
        now = tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(path))
    return path


def _beat_seconds(bar: dict, bpb: int) -> float:
    start = bar.get("grid_start_s", bar["start_s"])
    return (bar["end_s"] - start) / bpb
