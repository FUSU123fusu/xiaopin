#!/usr/bin/env python3
"""批量调节剧本的逐句语速/音高。

用途：贯口逐句加速、复读段逐句升调、包袱前放慢。

用法：
    # 查看第 92-120 句
    python scripts/tune.py work/script.json --show 92:120

    # 线性加速：第 92 句 +0%，到第 120 句 +25%
    python scripts/tune.py work/script.json --ramp 92:120 --rate-from 0 --rate-to 25

    # 整段设固定值
    python scripts/tune.py work/script.json --set 150:160 --rate -5 --pitch 2

    # 只改音高
    python scripts/tune.py work/script.json --ramp 250:258 --pitch-from 0 --pitch-to 10

不加 -o 时原地修改。行号从 1 开始，与 manifest 的 index 一致。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def fmt_rate(value: float) -> str:
    return f"{value:+.0f}%"


def fmt_pitch(value: float) -> str:
    return f"{value:+.0f}Hz"


def parse_range(text: str, total: int) -> tuple[int, int]:
    try:
        start_s, end_s = text.split(":")
        start, end = int(start_s), int(end_s)
    except ValueError:
        raise SystemExit(f"范围格式应为 START:END，收到 {text!r}")
    if start < 1 or end < start:
        raise SystemExit(f"非法范围 {text!r}")
    if end > total:
        print(f"[警告] 结束行 {end} 超过总句数 {total}，已截断", file=sys.stderr)
        end = total
    return start, end


def apply_ramp(lines: list[dict], start: int, end: int, *,
               rate_from=None, rate_to=None, pitch_from=None, pitch_to=None) -> None:
    span = max(1, end - start)
    for idx in range(start, end + 1):
        t = (idx - start) / span
        line = lines[idx - 1]
        if rate_from is not None:
            value = rate_from + (rate_to - rate_from) * t
            line["rate"] = fmt_rate(round(value))
        if pitch_from is not None:
            value = pitch_from + (pitch_to - pitch_from) * t
            line["pitch"] = fmt_pitch(round(value))


def apply_set(lines: list[dict], start: int, end: int, *,
              rate=None, pitch=None) -> None:
    for idx in range(start, end + 1):
        line = lines[idx - 1]
        if rate is not None:
            line["rate"] = fmt_rate(rate)
        if pitch is not None:
            line["pitch"] = fmt_pitch(pitch)


def show(lines: list[dict], start: int, end: int) -> None:
    for idx in range(start, end + 1):
        line = lines[idx - 1]
        override = ""
        if line.get("rate") or line.get("pitch"):
            override = f" [{line.get('rate', '-')}, {line.get('pitch', '-')}]"
        print(f"{idx:4d} {line['speaker']}{override} {line['text']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="批量调节剧本的逐句语速/音高")
    parser.add_argument("script", help="script.json 路径")
    parser.add_argument("-o", "--out", help="输出路径（默认原地修改）")
    parser.add_argument("--show", metavar="START:END", help="只查看，不修改")
    parser.add_argument("--ramp", metavar="START:END", help="线性渐变")
    parser.add_argument("--set", metavar="START:END", help="设为固定值")
    parser.add_argument("--rate", type=float, help="固定语速百分比，如 -5 / 20")
    parser.add_argument("--pitch", type=float, help="固定音高 Hz，如 -2 / 6")
    parser.add_argument("--rate-from", type=float)
    parser.add_argument("--rate-to", type=float)
    parser.add_argument("--pitch-from", type=float)
    parser.add_argument("--pitch-to", type=float)
    args = parser.parse_args()

    path = Path(args.script)
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = data["lines"]
    total = len(lines)

    if args.show:
        start, end = parse_range(args.show, total)
        show(lines, start, end)
        return 0

    if not args.ramp and not args.set:
        parser.error("需要 --show / --ramp / --set 之一")

    if args.ramp:
        start, end = parse_range(args.ramp, total)
        if args.rate_from is None and args.pitch_from is None:
            parser.error("--ramp 需要 --rate-from 或 --pitch-from")
        apply_ramp(
            lines, start, end,
            rate_from=args.rate_from,
            rate_to=args.rate_to if args.rate_to is not None else (args.rate_from or 0),
            pitch_from=args.pitch_from,
            pitch_to=args.pitch_to if args.pitch_to is not None else (args.pitch_from or 0),
        )
        print(f"已对第 {start}-{end} 句应用渐变")

    if args.set:
        start, end = parse_range(args.set, total)
        if args.rate is None and args.pitch is None:
            parser.error("--set 需要 --rate 或 --pitch")
        apply_set(lines, start, end, rate=args.rate, pitch=args.pitch)
        print(f"已对第 {start}-{end} 句设置固定值")

    out = Path(args.out) if args.out else path
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
