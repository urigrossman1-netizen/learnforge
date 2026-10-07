"""Regression tests for review findings (all offline)."""

import json
import os

import mido
import numpy as np
import pytest
import soundfile as sf

from drum_agent import chart, cli, config, pipeline, synth, transcribe, youtube


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Point every output folder at a temp dir."""
    for name in ("CHARTS_DIR", "AUDIO_DIR", "CACHE_DIR"):
        monkeypatch.setattr(config, name, tmp_path / name.lower())
    return tmp_path


def test_stop_before_chorus_restarts_the_bar_count():
    y, sr, truth = synth.make_song(gap=1.7)
    r = transcribe.transcribe(y, sr)
    assert r["tempo"]["bar_restarts"] >= 1
    verse = r["grooves"][r["sections"][0]["groove"]]["pattern"]
    assert verse["snare"] == [4, 12]  # backbeat stays on 2 and 4 before the stop
    labels = [s["label"] for s in r["sections"]]
    assert len(labels) == 3 and labels[0] == labels[2] != labels[1]
    scores = synth.score(truth["hits"], transcribe.hit_times(r))
    assert scores["kick"]["f1"] > 0.9 and scores["snare"]["f1"] > 0.9


def test_uniform_loop_is_one_section(monkeypatch):
    monkeypatch.setattr(synth, "FORM", [("verse", 16, synth.GROOVE_VERSE)])
    y, sr, _ = synth.make_song(backing=False)
    r = transcribe.transcribe(y, sr)
    assert [(s["first_bar"], s["last_bar"]) for s in r["sections"]] == [(1, 16)]


def test_too_short_audio_has_a_clear_error():
    with pytest.raises(ValueError, match="at least"):
        transcribe.transcribe(np.zeros(int(0.5 * 44100), dtype=np.float32), 44100)


def test_slugs_of_non_latin_titles_differ():
    a, b = config.slugify("Кино - Группа крови"), config.slugify("Кино - Кукушка")
    assert a != b and a.isascii() and b.isascii()
    assert config.slugify("Mötley Crüe - Kickstart My Heart") == "motley-crue-kickstart-my-heart"
    assert config.slugify("Кино - Кукушка") == b  # stable


def test_env_parsing(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("﻿SPOTIFY_CLIENT_ID=abc  # from dashboard\nSPOTIFY_CLIENT_SECRET='s3#cret'\n", encoding="utf-8")
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    config.load_env(env)
    assert os.environ["SPOTIFY_CLIENT_ID"] == "abc"
    assert os.environ["SPOTIFY_CLIENT_SECRET"] == "s3#cret"
    config.write_env({"SPOTIFY_CLIENT_ID": "new"}, env)
    assert env.read_text().count("SPOTIFY_CLIENT_ID") == 1


def test_cookie_spec_parsing(monkeypatch):
    monkeypatch.setenv("DRUM_AGENT_COOKIES_FROM_BROWSER", "Chrome:Profile 1")
    assert config.cookies_from_browser() == ("chrome", "Profile 1", None, None)
    monkeypatch.setenv("DRUM_AGENT_COOKIES_FROM_BROWSER", "none")
    assert config.cookies_from_browser() is None
    monkeypatch.setenv("DRUM_AGENT_COOKIES_FROM_BROWSER", "netscape")
    with pytest.raises(ValueError):
        config.cookies_from_browser()


def test_ranking_when_the_title_contains_a_filter_word():
    cands = [
        {"title": "Mötley Crüe - Live Wire (Live at Hammersmith 1984)", "channel": "Mötley Crüe", "duration_s": None},
        {"title": "Live Wire", "channel": "Mötley Crüe - Topic", "duration_s": None},
    ]
    assert youtube.rank(cands, None, "Mötley Crüe - Live Wire")[0]["channel"] == "Mötley Crüe - Topic"


@pytest.mark.parametrize("encoding", ["utf-16", "utf-8-sig"])
def test_batch_reads_windows_song_lists(project, tmp_path, monkeypatch, encoding):
    songs = tmp_path / "songs.txt"
    songs.write_text("# my list\nToto - Rosanna\n", encoding=encoding)
    seen = []

    def fake_resolve(song, **kw):
        seen.append(song)
        raise RuntimeError("offline")

    monkeypatch.setattr(pipeline, "resolve", fake_resolve)
    cli.main(["batch", str(songs)])
    assert seen == ["Toto - Rosanna"]


def test_rechart_by_slug_keeps_metadata_and_finds_user_file(project, tmp_path):
    y, sr, _ = synth.make_song()
    src = tmp_path / "take.wav"
    sf.write(str(src), y, sr)
    first = pipeline.chart_song(src, overrides={"title": "My Song", "artist": "Me"})
    meta_path = config.CHARTS_DIR / first["slug"] / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["spotify"] = {"title": "My Song", "url": "https://open.spotify.com/track/x"}
    meta_path.write_text(json.dumps(meta))
    again = pipeline.chart_song(first["slug"], bpm=96)  # slug, not a path
    saved = json.loads(meta_path.read_text())
    assert again["slug"] == first["slug"] and saved["spotify"]["url"].endswith("/x")
    assert saved["audio_file"] == str(src.resolve())


def test_wav_cache_is_keyed_by_file_not_name(project, tmp_path):
    y, sr, _ = synth.make_song()
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a, b = tmp_path / "a" / "track01.wav", tmp_path / "b" / "track01.wav"
    sf.write(str(a), y, sr)
    sf.write(str(b), y[: sr * 10], sr)
    assert pipeline._wav_path(a) != pipeline._wav_path(b)


def test_compound_meter_midi_and_header(tmp_path):
    result = {
        "tempo": {"bpm": 66.0, "beats_per_bar": 2, "subdivision": 3},
        "bars": [{"hits": {"kick": [[0, 0.7]], "snare": [[3, 0.7]]}}, {"hits": {"kick": [[0, 0.7]]}}],
    }
    mid = mido.MidiFile(chart.write_midi(result, tmp_path / "x.mid"))
    msgs = list(mid.tracks[0])
    sig = next(m for m in msgs if m.type == "time_signature")
    assert (sig.numerator, sig.denominator) == (6, 8)
    ticks, now = [], 0
    for m in msgs:
        now += m.time
        if m.type == "note_on" and m.velocity:
            ticks.append(now)
    assert ticks == [0, 720, 1440]  # beat 1, beat 2 (dotted quarter), next bar
    assert chart.meter(2, 3) == "6/8" and chart._clock(59.96) == "1:00.0"
