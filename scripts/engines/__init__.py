"""TTS 引擎注册表。统一接口：

    synthesize(text, voice, rate, pitch, out_path) -> None
"""

from __future__ import annotations

from pathlib import Path
import importlib
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "config.example.json"

ENGINES = {
    "edge": "engines.edge",
    "openai": "engines.openai",
    "local": "engines.local",
}


def load_config(path: str | Path | None = None) -> dict:
    """读配置。找不到 config.json 时回退到 example（仅 edge 可用）。"""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        cfg_path = EXAMPLE_CONFIG_PATH
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f)


def load_engine(name: str, config: dict):
    if name not in ENGINES:
        raise ValueError(f"未知 TTS 引擎: {name}（可选: {', '.join(ENGINES)}）")
    module = importlib.import_module(ENGINES[name])
    return module, config.get(name, {})
