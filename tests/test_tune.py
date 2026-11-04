"""测试：逐句语速/音高调节。"""

from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import tune  # noqa: E402
import tts  # noqa: E402


def make_lines(n=20):
    return [{"speaker": "甲", "text": f"第{i}句", "pause_after_ms": 100}
            for i in range(1, n + 1)]


def test_ramp_interpolates_rate():
    lines = make_lines()
    tune.apply_ramp(lines, 2, 10, rate_from=0, rate_to=20)
    assert lines[1]["rate"] == "+0%"
    assert lines[5]["rate"] == "+10%"
    assert lines[9]["rate"] == "+20%"


def test_ramp_interpolates_pitch():
    lines = make_lines()
    tune.apply_ramp(lines, 1, 5, pitch_from=0, pitch_to=8)
    assert lines[0]["pitch"] == "+0Hz"
    assert lines[2]["pitch"] == "+4Hz"
    assert lines[4]["pitch"] == "+8Hz"


def test_set_fixed_values():
    lines = make_lines()
    tune.apply_set(lines, 3, 6, rate=-5, pitch=2)
    for i in range(2, 6):
        assert lines[i]["rate"] == "-5%"
        assert lines[i]["pitch"] == "+2Hz"
    assert "rate" not in lines[0]


def test_parse_range_rejects_bad_input():
    import pytest
    with pytest.raises(SystemExit):
        tune.parse_range("10", 20)
    with pytest.raises(SystemExit):
        tune.parse_range("10:5", 20)


def test_parse_range_clamps_end(capsys):
    start, end = tune.parse_range("5:99", 20)
    assert (start, end) == (5, 20)


def test_line_level_rate_overrides_character(tmp_path, monkeypatch):
    """tts.py 应优先使用每句的 rate/pitch，而不是角色默认值。"""
    recorded = []

    def fake_synth(text, voice, rate, pitch, out_path):
        recorded.append((text, rate, pitch))
        wav = Path(out_path).with_suffix(".tmp.wav")
        with wave.open(str(wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(b"\x00" * 4410 * 2)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), str(out_path)],
                       check=True)

    import engines.edge as edge_mod
    monkeypatch.setattr(edge_mod, "synthesize", fake_synth)

    script = {
        "title": "调节测试",
        "style": "xiangsheng",
        "characters": [{"id": "甲", "name": "甲", "persona": "",
                        "voice": "zh-CN-YunjianNeural", "rate": "+0%", "pitch": "+0Hz"}],
        "lines": [
            {"speaker": "甲", "text": "普通句。", "pause_after_ms": 0},
            {"speaker": "甲", "text": "加速句。", "rate": "+25%", "pitch": "+6Hz",
             "pause_after_ms": 0},
        ],
    }
    tts.synthesize_script(script, tmp_path / "work", "edge", {"engine": "edge"})
    assert recorded[0][1:] == ("+0%", "+0Hz")
    assert recorded[1][1:] == ("+25%", "+6Hz")
