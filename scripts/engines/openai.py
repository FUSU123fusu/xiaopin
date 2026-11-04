"""OpenAI 兼容 TTS 引擎（也适用于任何实现 /v1/audio/speech 的服务）。"""

from __future__ import annotations

from pathlib import Path


def synthesize(text: str, voice: str, rate: str, pitch: str, out_path: Path) -> None:
    """注意：OpenAI TTS 不支持 rate/pitch 参数，这里只把 speed 映射到语速。

    voice 需使用 OpenAI 的音色名（alloy/echo/fable/onyx/nova/shimmer），
    请在 script.json 的 characters 中按引擎分别配置。
    """
    import requests

    from . import load_config

    cfg = load_config().get("openai", {})
    api_key = cfg.get("api_key")
    if not api_key or api_key.startswith("sk-..."):
        raise RuntimeError("openai 引擎需要在 config.json 中填写 api_key")

    base_url = cfg.get("base_url", "https://api.openai.com/v1").rstrip("/")
    model = cfg.get("model", "gpt-4o-mini-tts")
    fmt = cfg.get("format", "mp3")

    speed = 1.0
    if rate.endswith("%"):
        try:
            speed = 1.0 + float(rate[:-1]) / 100.0
        except ValueError:
            pass
    speed = max(0.25, min(4.0, speed))

    payload = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": fmt,
        "speed": speed,
    }
    resp = requests.post(
        f"{base_url}/audio/speech",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    Path(out_path).write_bytes(resp.content)
