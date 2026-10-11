"""Offline tests: synthetic song with known drums -> transcription, chart, MIDI, CLI."""

import json

import mido
import pytest
import soundfile as sf

from drum_agent import audio, cli, config, draft, performance, synth, transcribe, youtube
from drum_agent.drumchart import midi as chart_midi
from drum_agent.drumchart.parser import parse_chart


@pytest.fixture(scope="module")
def song():
    return synth.make_song()


@pytest.fixture(scope="module")
def result(song):
    y, sr, _ = song
    return transcribe.transcribe(y, sr)


def test_drum_hits_match_ground_truth(song, result):
    _, _, truth = song
    scores = synth.score(truth["hits"], transcribe.hit_times(result))
    assert scores["kick"]["f1"] >= 0.95
    assert scores["snare"]["f1"] >= 0.95
    assert scores["hihat"]["f1"] >= 0.85
    assert scores["crash"]["f1"] >= 0.6


def test_tempo_and_downbeat(song, result):
    _, _, truth = song
    assert result["tempo"]["bpm"] == pytest.approx(truth["bpm"], rel=0.02)
    assert result["tempo"]["first_downbeat_s"] == pytest.approx(truth["first_downbeat_s"], abs=0.05)


def test_form_grooves_and_fills(result):
    sections = [(s["first_bar"], s["last_bar"], s["label"]) for s in result["sections"]]
    assert sections == [(1, 8, "A"), (9, 16, "B"), (17, 20, "A")]
    fills = [b["index"] for b in result["bars"] if b.get("fill")]
    assert fills == [8, 16]
    verse = result["grooves"][result["sections"][0]["groove"]]["pattern"]
    assert verse == {k: v for k, v in synth.GROOVE_VERSE.items()}
    chorus = result["grooves"][result["sections"][1]["groove"]]["pattern"]
    assert chorus["kick"] == synth.GROOVE_CHORUS["kick"]
    assert chorus["snare"] == synth.GROOVE_CHORUS["snare"]


def test_shift_beats_moves_bar_lines(song):
    y, sr, truth = song
    shifted = transcribe.transcribe(y, sr, transcribe.Options(shift_beats=2))
    beat = 60 / truth["bpm"]
    first = shifted["tempo"]["first_downbeat_s"]
    assert min(abs(first - (truth["first_downbeat_s"] + 2 * beat)),
               abs(first - (truth["first_downbeat_s"] - 2 * beat))) < 0.06


def test_draft_chart_and_midi(result, tmp_path):
    text = draft.draft_chart(result, {"title": "Test Song", "artist": "Synth Band"}, "song.wav")
    chart = parse_chart(text)  # the draft is a valid chart
    assert [s.name for s in chart.sections] == ["Part A", "Part B", "Part A 2"]
    assert sum(1 for b in chart.bars if b.has_directive("fill")) == 2
    assert "source-kind: audio" in text and "title: Test Song" in text
    for mid in (mido.MidiFile(performance.write_midi(result, tmp_path / "p.mid")),
                mido.MidiFile(chart_midi.write_midi(chart, tmp_path / "c.mid"))):
        notes = [m for m in mid if m.type == "note_on" and m.velocity > 0]
        assert {m.note for m in notes} >= {36, 38, 42}
        assert all(m.channel == 9 for m in notes)


def test_draft_dynamics():
    bar = {"hits": {"snare": [[4, 1.0], [6, 0.3]], "kick": [[0, 1.0]], "hihat": [[2, 1.0]]}}
    rows = draft.bar_rows(bar, 4, 4)
    assert rows["SN"] == "---- X-g- ---- ----"  # accent and ghost only on the snare
    assert rows["BD"] == "x--- ---- ---- ----" and rows["HH"] == "--x- ---- ---- ----"


def test_ffmpeg_round_trip(song, tmp_path):
    y, sr, _ = song
    src = tmp_path / "a.wav"
    sf.write(str(src), y[: sr * 3], sr)
    mp3 = audio.to_mp3(src, tmp_path / "a.mp3")
    wav = audio.to_wav(mp3, tmp_path / "b.wav")
    assert audio.duration(wav) == pytest.approx(3.0, abs=0.1)
    assert sf.info(str(wav)).channels == 1


def test_youtube_ranking_prefers_studio_audio():
    cands = [
        {"title": "Queen - Another One Bites the Dust (Live Aid 1985)", "channel": "Queen", "duration_s": 260},
        {"title": "Another One Bites the Dust", "channel": "Queen - Topic", "duration_s": 216},
        {"title": "Another One Bites the Dust drum cover", "channel": "Drummer", "duration_s": 215},
    ]
    ranked = youtube.rank(cands, ref_duration=215.5, query="Queen - Another One Bites the Dust")
    assert ranked[0]["channel"] == "Queen - Topic"
    assert ranked[-1]["title"].endswith("drum cover") or "Live" in ranked[-1]["title"]


def test_chart_command_on_local_file(song, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "CHARTS_DIR", tmp_path / "charts")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    y, sr, _ = song
    src = tmp_path / "my-song.wav"
    sf.write(str(src), y, sr)
    assert cli.main(["analyze", str(src), "--title", "My Song", "--artist", "Me", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    analysis = json.loads(open(out["files"]["analysis"]).read())
    assert analysis["source"]["title"] == "My Song"
    assert out["bars"] == 20 and out["time"] == "4/4"
    page = open(out["files"]["page"], encoding="utf-8").read()
    assert "My Song" in page and 'id="chart-source"' in page and 'id="kit-data"' in page
