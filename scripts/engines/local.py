"""本地 TTS 引擎：POST 到本地 HTTP 服务（CosyVoice / Fish Audio / GPT-SoVITS 等）。

请求体约定（可按需改本文件适配你的服务）：
    {"text": ..., "voice": ..., "speed": ..., "format": ...}
响应体为音频二进制。
"""

from __future__ import annotations

from pathlib import Path


def synthesize(text: str, voice: str, rate: str, pitch: str, out_path: Path) -> None:
    import requests

    from . import load_config

    cfg = load_config().get("local", {})
    base_url = cfg.get("base_url", "http://127.0.0.1:9880/tts")
    fmt = cfg.get("format", "wav")

    speed = 1.0
    if rate.endswith("%"):
        try:
            speed = 1.0 + float(rate[:-1]) / 100.0
        except ValueError:
            pass

    payload = {"text": text, "voice": voice, "speed": speed, "format": fmt}
    resp = requests.post(base_url, json=payload, timeout=180)
    resp.raise_for_status()
    Path(out_path).write_bytes(resp.content)
