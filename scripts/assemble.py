#!/usr/bin/env python3
"""把 manifest.json 拼装成最终产物：mp3 / srt / 可读剧本 / 分角色音轨。

用法：
    python scripts/assemble.py work_dir [-o out_dir]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

SAMPLE_RATE = 44100
SAMPLE_WIDTH = 2  # 16 bit
CHANNELS = 1


def ms_to_frames(ms: int) -> int:
    return int(round(ms * SAMPLE_RATE / 1000))


def read_wav_frames(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wf:
        if wf.getnchannels() != CHANNELS or wf.getframerate() != SAMPLE_RATE:
            raise RuntimeError(f"{path.name} 不是 {SAMPLE_RATE}Hz 单声道")
        return wf.readframes(wf.getnframes())


SILENCE_CACHE: dict[int, bytes] = {}


def silence(ms: int) -> bytes:
    frames = ms_to_frames(ms)
    if frames not in SILENCE_CACHE:
        SILENCE_CACHE[frames] = b"\x00" * frames * SAMPLE_WIDTH * CHANNELS
    return SILENCE_CACHE[frames]


def write_wav(path: Path, chunks: list[bytes]) -> int:
    """写入 wav，返回总帧数。"""
    total = sum(len(c) // (SAMPLE_WIDTH * CHANNELS) for c in chunks)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        for chunk in chunks:
            wf.writeframes(chunk)
    return total


def encode_mp3(wav_path: Path, mp3_path: Path) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(wav_path),
         "-codec:a", "libmp3lame", "-q:a", "4", str(mp3_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 编码 mp3 失败: {result.stderr.strip()}")


def fmt_ts(ms: int) -> str:
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms_rem = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"


def build_srt(manifest: dict) -> str:
    blocks = []
    for n, line in enumerate(manifest["lines"], 1):
        start = line["start_ms"]
        end = start + line["duration_ms"]
        blocks.append(
            f"{n}\n{fmt_ts(start)} --> {fmt_ts(end)}\n{line['text']}\n"
        )
    return "\n".join(blocks)


def build_markdown(manifest: dict) -> str:
    chars = {c["id"]: c for c in manifest["characters"]}
    style_names = {
        "comedy": "喜剧小品", "xiangsheng": "双人相声",
        "talk": "播客对谈", "edu": "知识科普",
    }
    out = [f"# {manifest.get('title') or '未命名小品'}", ""]
    style = style_names.get(manifest.get("style"), manifest.get("style", ""))
    total_s = manifest["total_ms"] / 1000
    out.append(f"> 风格：{style}　时长：{total_s:.1f} 秒　引擎：{manifest.get('engine')}")
    out.append("")
    out.append("## 角色")
    for c in manifest["characters"]:
        out.append(f"- **{c['id']}｜{c.get('name', c['id'])}**：{c.get('persona', '')}"
                   f"（{c.get('voice', '')}）")
    out.append("")
    out.append("## 台词")
    out.append("")
    for line in manifest["lines"]:
        c = chars[line["speaker"]]
        name = c.get("name") or line["speaker"]
        emotion = f"（{line['emotion']}）" if line.get("emotion") else ""
        pause = line.get("pause_after_ms") or 0
        tail = f"　*［停顿 {pause}ms］*" if pause >= 300 else ""
        out.append(f"**{name}**{emotion}：{line['text']}{tail}")
        out.append("")
    return "\n".join(out)


def build_tracks(manifest: dict, work_dir: Path, tracks_dir: Path) -> list[Path]:
    """为每个角色生成一条音轨：只保留该角色的声音，其余位置为等长静音。"""
    chars = [c["id"] for c in manifest["characters"]]
    written = []
    for cid in chars:
        chunks = []
        for line in manifest["lines"]:
            if line["speaker"] == cid:
                chunks.append(read_wav_frames(work_dir / line["wav"]))
            else:
                chunks.append(silence(line["duration_ms"]))
            if line.get("pause_after_ms"):
                chunks.append(silence(line["pause_after_ms"]))
        wav_path = tracks_dir / f"{cid}.wav"
        write_wav(wav_path, chunks)
        mp3_path = tracks_dir / f"{cid}.mp3"
        encode_mp3(wav_path, mp3_path)
        wav_path.unlink()
        written.append(mp3_path)
    return written


def slugify(title: str) -> str:
    slug = re.sub(r"[\\/:*?\"<>|\s]+", "-", title or "xiaopin").strip("-")
    return slug[:60] or "xiaopin"


def assemble(work_dir: Path, out_dir: Path) -> dict:
    manifest_path = work_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"找不到 {manifest_path}，请先运行 tts.py")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest["lines"]:
        raise RuntimeError("没有任何成功合成的句子")

    out_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(manifest.get("title", ""))

    # 主音轨
    chunks = []
    for line in manifest["lines"]:
        chunks.append(read_wav_frames(work_dir / line["wav"]))
        if line.get("pause_after_ms"):
            chunks.append(silence(line["pause_after_ms"]))
    main_wav = work_dir / "main.wav"
    frames = write_wav(main_wav, chunks)
    main_mp3 = out_dir / f"{slug}.mp3"
    encode_mp3(main_wav, main_mp3)

    # 字幕
    srt_path = out_dir / f"{slug}.srt"
    srt_path.write_text(build_srt(manifest), encoding="utf-8")

    # 可读剧本
    md_path = out_dir / f"{slug}.md"
    md_path.write_text(build_markdown(manifest), encoding="utf-8")

    # 分角色音轨（只覆盖本次角色，不清空目录，避免误删其他作品的音轨）
    tracks_dir = out_dir / "tracks"
    tracks_dir.mkdir(exist_ok=True)
    tracks = build_tracks(manifest, work_dir, tracks_dir)

    # 一致性校验：主音轨时长 vs manifest 推算
    actual_ms = int(round(frames * 1000 / SAMPLE_RATE))
    drift = abs(actual_ms - manifest["total_ms"])
    if drift > 100:
        print(f"[警告] 音频时长与推算偏差 {drift}ms", file=sys.stderr)

    return {
        "audio": str(main_mp3),
        "srt": str(srt_path),
        "script": str(md_path),
        "tracks": [str(t) for t in tracks],
        "duration_s": round(actual_ms / 1000, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="拼装最终产物")
    parser.add_argument("work_dir", help="tts.py 产出的工作目录")
    parser.add_argument("-o", "--out-dir", default="out", help="输出目录（默认 out）")
    args = parser.parse_args()

    try:
        result = assemble(Path(args.work_dir), Path(args.out_dir))
    except Exception as exc:
        print(f"拼装失败: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
