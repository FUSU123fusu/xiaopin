"""edge-tts 引擎：免费、无需 key、无需显卡。默认引擎。"""

from __future__ import annotations

import asyncio
from pathlib import Path


async def _synth(text: str, voice: str, rate: str, pitch: str, out_path: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(out_path))


def synthesize(text: str, voice: str, rate: str, pitch: str, out_path: Path) -> None:
    asyncio.run(_synth(text, voice, rate, pitch, Path(out_path)))
