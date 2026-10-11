"""Chart pages in a real browser (skipped when Node.js Playwright is not available)."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import soundfile as sf

from drum_agent import synth
from drum_agent.drumchart.render import load, render_html

HERE = Path(__file__).parent
CANDIDATES = [os.environ.get("PLAYWRIGHT_NODE_MODULE", ""), "/opt/node-tools/node_modules/playwright/index.mjs"]
PLAYWRIGHT = next((p for p in CANDIDATES if p and Path(p).exists()), None)
pytestmark = pytest.mark.skipif(not (PLAYWRIGHT and shutil.which("node")), reason="needs Node.js + Playwright")


def _drive(page: Path, audio: Path | None = None) -> dict:
    cmd = ["node", str(HERE / "browser" / "player.mjs"), PLAYWRIGHT, str(page)] + ([str(audio)] if audio else [])
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    path = tmp_path_factory.mktemp("page") / "night-drive.html"
    path.write_text(render_html(load(HERE.parent / "examples" / "night-drive.drums")), encoding="utf-8")
    return path


def test_real_drum_playback_and_jump(page):
    r = _drive(page)
    assert r["errors"] == [] and r["decoded"]["bad"] == 0 and r["decoded"]["ok"] >= 9
    assert r["playing"]["playing"] and not r["playing"]["recording"]
    assert r["jumped"]["cur"] == 5 and r["jumped"]["highlighted"] == "6"


def test_play_along_with_a_recording(page, tmp_path):
    y, sr, _ = synth.make_song()
    wav = tmp_path / "take.wav"
    sf.write(str(wav), y, sr)
    r = _drive(page, wav)
    assert r["errors"] == []
    assert r["playing"]["recording"] and r["playing"]["t"] > 1.0  # the recording is playing
    assert r["jumped"]["cur"] == 5 and r["jumped"]["highlighted"] == "6"
    assert 10.5 < r["jumped"]["t"] < 13  # bar 6 at 112 BPM starts 10.7 s in; the file was sought there
