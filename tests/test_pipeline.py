"""测试：抽取、字幕时间轴、端到端（mock TTS）。"""

from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import assemble  # noqa: E402
import extract  # noqa: E402
import tts  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def make_fixtures():
    FIXTURES.mkdir(exist_ok=True)
    md = FIXTURES / "sample.md"
    md.write_text(
        "# 为什么我们会拖延\n\n"
        "拖延不是懒，是情绪调节失败。当我们面对一项任务时，如果它引发了焦虑、"
        "无聊或自我怀疑，大脑会选择短期舒服的逃避，而不是长期有利的行动。"
        "这不是意志力的问题，而是情绪管理的问题——我们逃避的不是任务本身，"
        "而是任务带来的那种不舒服的感觉。\n\n"
        "解决办法不是逼自己更狠，而是降低启动成本：把任务拆到小得不可能失败，"
        "并且允许自己先做一个很烂的版本。当你开始行动之后，焦虑会自然下降，"
        "因为大脑发现这件事并没有想象中那么可怕。这就是所谓的「两分钟法则」——"
        "任何任务，先做两分钟再说。\n\n"
        "另外，给自己设定明确的停止时间也很重要。如果一件事没有终点，"
        "大脑就会一直拖着不肯开始，因为它感觉这活儿永远干不完。"
        "给任务加一个明确的边界，拖延的动力就会明显减弱。\n",
        encoding="utf-8",
    )
    yield


def test_extract_markdown():
    result = extract.extract(str(FIXTURES / "sample.md"))
    assert result["title"] == "为什么我们会拖延"
    assert result["char_count"] > 100
    assert "拖延不是懒" in result["text"]
    assert result["warnings"] == []


def test_extract_short_text_warns(tmp_path):
    p = tmp_path / "short.txt"
    # 150 字：高于 100（不是扫描件），低于 300（偏少）
    p.write_text("这是一段测试文本。" * 18, encoding="utf-8")
    result = extract.extract(str(p))
    assert result["warnings"]
    assert "偏少" in result["warnings"][0]


def test_extract_tiny_text_mentions_ocr(tmp_path):
    p = tmp_path / "tiny.txt"
    p.write_text("太短了。", encoding="utf-8")
    result = extract.extract(str(p))
    assert result["warnings"]
    assert "OCR" in result["warnings"][0]


def test_extract_missing_file():
    with pytest.raises(FileNotFoundError):
        extract.extract("no_such_file.pdf")


def test_validate_script_catches_bad_speaker():
    script = {
        "characters": [{"id": "A", "name": "甲"}],
        "lines": [{"speaker": "B", "text": "你好"}],
    }
    errors = tts.validate_script(script)
    assert any("speaker" in e for e in errors)


def test_validate_script_catches_long_line():
    script = {
        "characters": [{"id": "A", "name": "甲"}],
        "lines": [{"speaker": "A", "text": "字" * 100}],
    }
    errors = tts.validate_script(script)
    assert any("80" in e for e in errors)


def test_srt_timeline_monotonic_and_aligned(tmp_path):
    """字幕时间轴单调递增，总长与音频一致。"""
    manifest = {
        "title": "测试",
        "style": "comedy",
        "engine": "mock",
        "total_ms": 3000,
        "characters": [{"id": "A", "name": "甲", "persona": "", "voice": ""}],
        "lines": [
            {"index": 1, "speaker": "A", "text": "第一句", "emotion": "",
             "start_ms": 0, "duration_ms": 1000, "pause_after_ms": 500, "wav": "x.wav"},
            {"index": 2, "speaker": "A", "text": "第二句", "emotion": "",
             "start_ms": 1500, "duration_ms": 1000, "pause_after_ms": 500, "wav": "x.wav"},
        ],
    }
    srt = assemble.build_srt(manifest)
    assert "00:00:00,000 --> 00:00:01,000" in srt
    assert "00:00:01,500 --> 00:00:02,500" in srt
    # 单调
    starts = [line["start_ms"] for line in manifest["lines"]]
    assert starts == sorted(starts)
    # 最后一句结束时间 ≤ 总时长
    last = manifest["lines"][-1]
    assert last["start_ms"] + last["duration_ms"] <= manifest["total_ms"]


def test_end_to_end_with_mock_engine(tmp_path, monkeypatch):
    """用真实 ffmpeg 生成正弦波音频，跑通全流程。"""

    def fake_synth(text, voice, rate, pitch, out_path):
        # 生成一段与文字长度成正比的静音 wav，再交给 ffmpeg 转 mp3
        frames = len(text) * 100
        wav = tmp_path / "tmp.wav"
        with wave.open(str(wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(b"\x00" * frames * 2)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), str(out_path)],
                       check=True)

    import engines.edge as edge_mod
    monkeypatch.setattr(edge_mod, "synthesize", fake_synth)

    script = {
        "title": "端到端测试",
        "style": "comedy",
        "characters": [
            {"id": "A", "name": "老张", "persona": "轴",
             "voice": "zh-CN-liaoning-XiaobeiNeural", "rate": "+0%", "pitch": "+0Hz"},
            {"id": "B", "name": "小刘", "persona": "机灵",
             "voice": "zh-CN-YunxiNeural", "rate": "+0%", "pitch": "+0Hz"},
        ],
        "lines": [
            {"speaker": "A", "text": "我跟你说这事不能这么办。", "pause_after_ms": 400},
            {"speaker": "B", "text": "那您说怎么办？", "pause_after_ms": 600},
            {"speaker": "A", "text": "不能办。", "pause_after_ms": 800},
        ],
    }
    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")

    config = {"engine": "edge", "edge": {}}
    work = tmp_path / "work"
    manifest = tts.synthesize_script(script, work, "edge", config)
    assert len(manifest["lines"]) == 3
    assert manifest["failures"] == []
    assert manifest["total_ms"] > 0

    out = tmp_path / "out"
    result = assemble.assemble(work, out)
    assert Path(result["audio"]).exists()
    assert Path(result["srt"]).exists()
    assert Path(result["script"]).exists()
    assert len(result["tracks"]) == 2
    assert result["duration_s"] > 0

    # 主音轨时长应与 manifest 推算一致（<100ms 偏差）
    manifest_ms = manifest["total_ms"]
    assert abs(result["duration_s"] * 1000 - manifest_ms) < 100

    md = Path(result["script"]).read_text(encoding="utf-8")
    assert "老张" in md and "小刘" in md
