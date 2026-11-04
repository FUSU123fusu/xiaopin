#!/usr/bin/env python3
"""导入已有的中文剧本（Markdown / 纯文本）为 script.json。

识别的格式：
    **甲**（情绪）：台词
    **甲**：台词
    > 数来宝/贯口的唱词（归属于当前说话人）

自动完成：去掉舞台提示、按标点切分长句、按标点设置停顿、
【抖包袱】前一句自动加长停顿。

用法：
    python scripts/import_script.py 剧本.md -o work/script.json \\
        --voice-a zh-CN-YunjianNeural --voice-b zh-CN-XiaoyiNeural
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MAX_LEN = 45
SPEAKER_RE = re.compile(r"^\*\*(?P<name>[^*]{1,8}?)\*\*\s*(?P<rest>.*)$")
EMOTION_RE = re.compile(r"^[（(](?P<emotion>[^）)]*)[）)]\s*(?P<text>.*)$")
VALID_NAME_RE = re.compile(r"^[一-龥A-Za-z]{1,4}$")
PUNCT_END = "。！？…—"
PUNCT_ALL = "。！？；，、：…—"


def clean_inline(text: str) -> str:
    text = text.replace("**", "").replace("*", "")
    text = re.sub(r"`([^`]*)`", r"\1", text)
    return text.strip()


def split_text(text: str, max_len: int = MAX_LEN) -> list[str]:
    """先按句末标点切，仍然过长再按逗号切。"""
    text = text.strip()
    if len(text) <= max_len:
        return [text] if text else []

    chunks: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in PUNCT_END and len(buf) >= max_len * 0.5:
            chunks.append(buf)
            buf = ""
    if buf:
        chunks.append(buf)

    # 二次切分：单块仍超长，按逗号等切
    result: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_len:
            result.append(chunk)
            continue
        buf = ""
        for ch in chunk:
            buf += ch
            if ch in PUNCT_ALL and len(buf) >= max_len * 0.6:
                result.append(buf)
                buf = ""
        if buf:
            result.append(buf)

    # 三次兜底：硬切
    final: list[str] = []
    for chunk in result:
        while len(chunk) > max_len * 1.6:
            final.append(chunk[:max_len])
            chunk = chunk[max_len:]
        if chunk.strip():
            final.append(chunk)
    return [c.strip() for c in final if c.strip()]


def pause_for(text: str) -> int:
    text = text.rstrip()
    if text.endswith(("？", "?")):
        return 450
    if text.endswith(("！", "!")):
        return 500
    if text.endswith("—"):
        return 400
    if text.endswith(("。", "…")):
        return 550
    return 300


def slice_body(text: str) -> str:
    """只保留正戏部分：从第一个「第X折/第X幕/第X场」标题到「演出提示」之前。"""
    lines = text.splitlines()
    start = None
    end = len(lines)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if start is None and re.match(r"^#{1,4}\s*第[一二三四五六七八九十百\d]+[折幕场节回]", stripped):
            start = i
        elif start is not None and re.match(r"^#{1,4}\s*(演出提示|附录|事实依据|风险红线|创作说明)", stripped):
            end = i
            break
    return "\n".join(lines[start:end]) if start is not None else text


def count_speakers(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in text.splitlines():
        m = SPEAKER_RE.match(line.strip())
        if m:
            name = m.group("name").strip()
            if VALID_NAME_RE.match(name):
                counts[name] = counts.get(name, 0) + 1
    return counts


def parse(text: str) -> tuple[list[dict], list[str]]:
    text = slice_body(text)
    counts = count_speakers(text)
    # 至少出现 3 次的短名字才当作说话人，过滤「时长」「风格」这类字段
    valid_names = {name for name, n in counts.items() if n >= 3}

    lines_out: list[dict] = []
    speakers: list[str] = []
    current = None

    def add_line(text: str, emotion: str = "") -> None:
        nonlocal current
        if current is None:
            return
        for chunk in split_text(text):
            lines_out.append({
                "speaker": current,
                "text": chunk,
                "emotion": emotion,
                "pause_after_ms": pause_for(chunk),
            })

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("## ", "# ")):
            current = None
            continue
        if line.startswith("---"):
            continue

        # 【抖包袱】等提示：给上一句加长停顿
        if "【" in line and "】" in line and not line.startswith("**"):
            if lines_out:
                lines_out[-1]["pause_after_ms"] = max(
                    lines_out[-1]["pause_after_ms"], 800
                )
            continue

        # 引用块 = 唱词/贯口，归当前说话人
        if line.startswith(">"):
            body = line.lstrip(">").strip()
            if not body or "【" in body:
                continue
            add_line(clean_inline(body))
            continue

        m = SPEAKER_RE.match(line)
        if m:
            name = m.group("name").strip()
            if name not in valid_names:
                continue
            rest = m.group("rest").strip()
            if name not in speakers:
                speakers.append(name)
            current = name

            emotion = ""
            rest = re.sub(r"^[：:]\s*", "", rest)
            em = EMOTION_RE.match(rest)
            if em:
                emotion = em.group("emotion").strip()
                rest = re.sub(r"^[：:]\s*", "", em.group("text").strip())
            if rest:
                add_line(clean_inline(rest), emotion)
            continue

        # 普通续行，归当前说话人
        if line.startswith(("*", "|", " ", "　")):
            continue
        if current:
            add_line(clean_inline(line))

    return lines_out, speakers


def main() -> int:
    parser = argparse.ArgumentParser(description="导入已有剧本为 script.json")
    parser.add_argument("source", help="剧本 Markdown/文本路径")
    parser.add_argument("-o", "--out", default="work/script.json")
    parser.add_argument("--title", help="标题（默认取第一行 # 标题）")
    parser.add_argument("--style", default="xiangsheng")
    parser.add_argument("--voice-a", default="zh-CN-YunjianNeural")
    parser.add_argument("--voice-b", default="zh-CN-XiaoyiNeural")
    parser.add_argument("--rate-a", default="+2%")
    parser.add_argument("--rate-b", default="+0%")
    args = parser.parse_args()

    path = Path(args.source)
    raw = path.read_text(encoding="utf-8", errors="replace")

    title = args.title
    if not title:
        for line in raw.splitlines():
            if line.startswith("# "):
                title = line[2:].strip().strip("*").strip().strip("《》")
                break
    title = title or path.stem

    lines, speakers = parse(raw)
    if not lines:
        print("没有解析出任何台词，请检查剧本格式", file=sys.stderr)
        return 1
    if len(speakers) > 2:
        print(f"[注意] 检测到 {len(speakers)} 个说话人: {speakers}，"
              "当前只配置了前两位的音色", file=sys.stderr)

    personas = {
        speakers[0]: "逗哏，语速偏快，情绪起伏大",
        speakers[1] if len(speakers) > 1 else "B": "捧哏，语气平稳，客气",
    }
    characters = []
    for i, name in enumerate(speakers[:2]):
        characters.append({
            "id": name,
            "name": name,
            "persona": personas.get(name, ""),
            "voice": args.voice_a if i == 0 else args.voice_b,
            "rate": args.rate_a if i == 0 else args.rate_b,
            "pitch": "+0Hz",
        })
    # 多于两人时补默认音色，避免 speaker 校验失败
    for name in speakers[2:]:
        characters.append({
            "id": name, "name": name, "persona": "",
            "voice": "zh-CN-YunyangNeural", "rate": "+0%", "pitch": "+0Hz",
        })

    script = {
        "title": title,
        "style": args.style,
        "source": {"file": str(path), "char_count": len(re.sub(r"\s", "", raw))},
        "characters": characters,
        "lines": lines,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

    total_chars = sum(len(l["text"]) for l in lines)
    print(f"已写入 {out}")
    print(f"说话人: {speakers}")
    print(f"台词: {len(lines)} 句，{total_chars} 字，"
          f"预计 {total_chars / 4.5 / 60:.1f} 分钟")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
