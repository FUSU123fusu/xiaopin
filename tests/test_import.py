"""测试：已有剧本导入。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import import_script  # noqa: E402

SAMPLE = """# 《测试相声》

**风格**：南派相声
**时长**：约 5 分钟

## 人物

**甲（逗哏）**：穿格子衫。
**乙（捧哏）**：穿黑西装。

## 第一折 · 垫话

**甲**（上台抱拳）：各位，今天说个新鲜事儿。
**乙**：哦，您要聊什么？
**甲**：聊什么聊，我给它说一段。
**乙**：给它说相声？
**甲**（清清嗓子）：咱们南派有个老规矩。

> 说模型，拉洋片儿，
> 一张洋片两分钱。

> 【抖包袱】这句要停一拍

**乙**：那到底谁先得着？
**甲**：谁达标早谁得。

## 演出提示

**甲**：这段不该被解析。
"""


def test_slice_body_excludes_meta_sections():
    body = import_script.slice_body(SAMPLE)
    assert "第一折" in body
    assert "演出提示" not in body
    assert "这段不该被解析" not in body
    assert "时长" not in body


def test_count_speakers_filters_fields():
    counts = import_script.count_speakers(import_script.slice_body(SAMPLE))
    assert set(counts) == {"甲", "乙"}


def test_parse_produces_clean_lines():
    lines, speakers = import_script.parse(SAMPLE)
    assert speakers == ["甲", "乙"]
    assert all(not l["text"].startswith("：") for l in lines)
    assert all(len(l["text"]) <= import_script.MAX_LEN * 2 for l in lines)
    # 舞台提示被抽进 emotion，不混进台词
    first = lines[0]
    assert first["emotion"] == "上台抱拳"
    assert first["text"] == "各位，今天说个新鲜事儿。"
    # 引用块（数来宝）归属甲
    verse = [l for l in lines if "拉洋片" in l["text"]]
    assert verse and verse[0]["speaker"] == "甲"
    # 【抖包袱】前一句停顿被加长
    before = [l for l in lines if "两张洋片两分钱" in l["text"] or "一张洋片两分钱" in l["text"]]
    assert before and before[0]["pause_after_ms"] >= 800


def test_short_text_not_split():
    text = "这是第一句话。这是第二句话！这是第三句话？"
    assert import_script.split_text(text) == [text]


def test_long_text_split_keeps_punctuation():
    text = "这是用来测试切分逻辑的一句话。" * 8  # 128 字，必然触发切分
    chunks = import_script.split_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= import_script.MAX_LEN * 2 for c in chunks)
    assert chunks[0].endswith("。")
    # 拼回去不能丢字
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_pause_heuristics():
    assert import_script.pause_for("你说什么？") == 450
    assert import_script.pause_for("好！") == 500
    assert import_script.pause_for("完了。") == 550
