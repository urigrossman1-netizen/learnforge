"""Bad input gets one clear sentence (no traceback), and every run leaves a job record."""

import json

import numpy as np
import pytest
import soundfile as sf

from drum_agent import audio, cli, config, synth


@pytest.fixture
def library(tmp_path, monkeypatch):
    for name in ("CHARTS_DIR", "AUDIO_DIR", "CACHE_DIR"):
        monkeypatch.setattr(config, name, tmp_path / name.lower())
    return tmp_path


@pytest.mark.parametrize(
    "make, message",
    [
        (lambda p: p.write_text("not audio"), "cannot read it"),
        (lambda p: p.write_bytes(b""), "is empty"),
        (lambda p: sf.write(str(p), np.zeros(22050, dtype="float32"), 44100), "at least 2 s"),
        (lambda p: sf.write(str(p), np.zeros(44100 * 5, dtype="float32"), 44100), "silent"),
        (lambda p: None, "does not exist"),
    ],
)
def test_bad_audio_gets_a_plain_error(library, tmp_path, capsys, make, message):
    path = tmp_path / "input.wav"
    make(path)
    assert cli.main(["analyze", str(path)]) == 2
    err = capsys.readouterr().err
    assert message in err and "Traceback" not in err


def test_failed_run_records_where_it_stopped(library, tmp_path):
    path = tmp_path / "quiet.wav"
    sf.write(str(path), np.zeros(44100 * 5, dtype="float32"), 44100)
    assert cli.main(["analyze", str(path)]) == 2
    job = json.loads((config.CHARTS_DIR / "quiet" / "job.json").read_text())
    assert job["status"] == "failed" and "silent" in job["error"]
    assert [s["status"] for s in job["stages"]] == ["done", "failed"]


def test_successful_run_records_stages_and_engine(library, tmp_path, capsys):
    y, sr, _ = synth.make_song()
    path = tmp_path / "song.wav"
    sf.write(str(path), y, sr)
    assert cli.main(["analyze", str(path), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    job = json.loads((config.CHARTS_DIR / out["slug"] / "job.json").read_text())
    assert job["status"] == "done" and job["bars"] == out["bars"]
    assert [s["stage"] for s in job["stages"]] == ["check audio", "decode", "transcribe", "write chart", "render page"]
    assert job["engine"].startswith("drum-agent ")


def test_inspect_warns_about_low_quality(tmp_path):
    path = tmp_path / "phone.wav"
    y, sr, _ = synth.make_song()
    sf.write(str(path), y[::4], sr // 4)  # 11 kHz sample rate
    info = audio.inspect(path)
    assert info["sample_rate"] == sr // 4 and any("low sample rate" in w for w in info["warnings"])
