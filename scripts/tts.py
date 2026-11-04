#!/usr/bin/env python3
"""按 script.json 逐句合成音频，产出 manifest.json。

用法：
    python scripts/tts.py script.json [-o work_dir] [--engine edge] [--config config.json]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engines import load_config, load_engine  # noqa: E402

MAX_RETRIES = 3
RETRY_DELAY = 2.0


def probe_duration_ms(path: Path) -> int:
    """用 ffprobe 取真实音频时长（毫秒）。"""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {result.stderr.strip()}")
    return int(round(float(result.stdout.strip()) * 1000))


def to_wav(src: Path, dst: Path) -> None:
    """统一转成 44100Hz 单声道 16bit wav，便于精确拼接。"""
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-i", str(src),
            "-ac", "1", "-ar", "44100", "-sample_fmt", "s16", str(dst),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 转 wav 失败: {result.stderr.strip()}")


def validate_script(script: dict) -> list[str]:
    errors = []
    chars = script.get("characters") or []
    if not chars:
        errors.append("characters 为空")
    ids = {c.get("id") for c in chars}
    if len(ids) != len(chars):
        errors.append("characters 的 id 有重复")
    lines = script.get("lines") or []
    if not lines:
        errors.append("lines 为空")
    for i, line in enumerate(lines, 1):
        if line.get("speaker") not in ids:
            errors.append(f"第 {i} 句的 speaker={line.get('speaker')!r} 不在 characters 中")
        if not str(line.get("text", "")).strip():
            errors.append(f"第 {i} 句 text 为空")
        if len(line.get("text", "")) > 80:
            errors.append(f"第 {i} 句超过 80 字，建议拆句（当前 {len(line['text'])} 字）")
    return errors


def synthesize_script(script: dict, work_dir: Path, engine_name: str, config: dict) -> dict:
    module, engine_cfg = load_engine(engine_name, config)
    audio_dir = work_dir / "audio"
    wav_dir = work_dir / "wav"
    audio_dir.mkdir(parents=True, exist_ok=True)
    wav_dir.mkdir(parents=True, exist_ok=True)

    chars = {c["id"]: c for c in script["characters"]}
    lines_out = []
    failures = []
    cursor_ms = 0
    total = len(script["lines"])

    for idx, line in enumerate(script["lines"], 1):
        speaker = line["speaker"]
        ch = chars[speaker]
        text = line["text"].strip()
        pause = int(line.get("pause_after_ms") or 0)

        stem = f"line_{idx:04d}"
        mp3_path = audio_dir / f"{stem}.mp3"
        wav_path = wav_dir / f"{stem}.wav"

        voice = ch.get("voice", "zh-CN-XiaoxiaoNeural")
        rate = ch.get("rate", "+0%")
        pitch = ch.get("pitch", "+0Hz")

        ok = False
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                module.synthesize(text, voice, rate, pitch, mp3_path)
                if not mp3_path.exists() or mp3_path.stat().st_size == 0:
                    raise RuntimeError("生成了空音频")
                ok = True
                break
            except Exception as exc:
                last_err = exc
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
        if not ok:
            failures.append({"line": idx, "error": str(last_err)})
            print(f"[{idx}/{total}] 失败: {last_err}", file=sys.stderr)
            continue

        try:
            to_wav(mp3_path, wav_path)
            duration = probe_duration_ms(wav_path)
        except Exception as exc:
            failures.append({"line": idx, "error": str(exc)})
            print(f"[{idx}/{total}] 转换失败: {exc}", file=sys.stderr)
            continue

        lines_out.append({
            "index": idx,
            "speaker": speaker,
            "text": text,
            "emotion": line.get("emotion", ""),
            "start_ms": cursor_ms,
            "duration_ms": duration,
            "pause_after_ms": pause,
            "wav": str(wav_path.relative_to(work_dir)).replace("\\", "/"),
        })
        cursor_ms += duration + pause
        print(f"[{idx}/{total}] {speaker} {duration}ms", file=sys.stderr)

    manifest = {
        "title": script.get("title", ""),
        "style": script.get("style", ""),
        "engine": engine_name,
        "total_ms": cursor_ms,
        "characters": script["characters"],
        "lines": lines_out,
        "failures": failures,
    }
    (work_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="按剧本合成音频")
    parser.add_argument("script", help="script.json 路径")
    parser.add_argument("-o", "--out-dir", default="work", help="工作目录（默认 work）")
    parser.add_argument("--engine", help="覆盖 config 中的引擎")
    parser.add_argument("--config", help="config.json 路径")
    args = parser.parse_args()

    script = json.loads(Path(args.script).read_text(encoding="utf-8"))
    errors = validate_script(script)
    if errors:
        for e in errors:
            print(f"[剧本错误] {e}", file=sys.stderr)
        return 1

    config = load_config(args.config)
    engine_name = args.engine or config.get("engine", "edge")

    work_dir = Path(args.out_dir)
    # 只清理上次的音频产物，保留剧本和 source.json
    for sub in ("audio", "wav"):
        target = work_dir / sub
        if target.exists():
            shutil.rmtree(target)
    work_dir.mkdir(parents=True, exist_ok=True)

    manifest = synthesize_script(script, work_dir, engine_name, config)
    total_s = manifest["total_ms"] / 1000
    print(f"\n完成：{len(manifest['lines'])} 句，总长 {total_s:.1f} 秒，"
          f"失败 {len(manifest['failures'])} 句", file=sys.stderr)
    if manifest["failures"]:
        print("失败的句子会在最终音频中以静音替代，请检查。", file=sys.stderr)
    return 0 if manifest["lines"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
