"""Voz default: edge-tts (servicio de terceros, requiere red, NO offline).

Protocolo real verificado: CLI `edge-tts --voice V --text T
--write-media OUT --write-subtitles SUBS` (flags confirmados con
`edge-tts --help` en 7.2.7) + duración vía `ffprobe -v error
-show_entries format=duration -of json` (JSON, no parseo de stderr como
el origen). words_path = subtítulos VTT con word boundaries.
verified=False hasta micro-síntesis live documentada.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from stickman.errors import ProviderError
from stickman.provider_base import Requirement
from stickman.voice.base import VoiceProvider, require_live


def _default_run(argv, **kw):
    return subprocess.run(argv, check=False, capture_output=True, text=True,
                          **kw)


def probe_duration(run, media: Path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of", "json", str(media)],
            timeout=60)
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except (ValueError, KeyError, TypeError) as e:
        raise ProviderError(f"voz edge: ffprobe sin duración ({e})")


class EdgeVoice(VoiceProvider):
    """edge-tts del usuario (su red). Sin fallback a otra voz."""

    name = "edge"
    verified = False

    def __init__(self, *, _run=None):
        self._injected = _run is not None
        self._run = _run or _default_run

    def requirements(self) -> list:
        return [Requirement(kind="network",
                            label="Red (edge-tts es servicio online)"),
                Requirement(kind="cli",
                            label="edge-tts instalable (`pip install edge-tts`)",
                            official=False, verified=False),
                Requirement(kind="model",
                            label="Voz configurable (default "
                                  "en-US-AndrewNeural)")]

    def synthesize(self, text: str, out: Path, *, voice: str,
                   speed: float, live: bool = False) -> dict:
        require_live(live, "voz edge")
        if not text or not text.strip():
            raise ProviderError("voz edge: texto vacío")
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        subs = out.with_suffix(".vtt")
        rate = f"{(speed - 1.0) * 100:+.0f}%"
        if self._injected:
            r = self._run(["edge-tts", "--voice", voice, "--text", text,
                           "--rate", rate, "--write-media", str(out),
                           "--write-subtitles", str(subs)], timeout=180)
            if r.returncode != 0 or not out.exists():
                raise ProviderError("Edge synthesis failed; check network and voice.")
        else:
            import asyncio
            import edge_tts
            async def stream():
                words=[]
                communicate=edge_tts.Communicate(text,voice,rate=rate,boundary="WordBoundary")
                with out.open("wb") as f:
                    async for chunk in communicate.stream():
                        if chunk["type"]=="audio": f.write(chunk["data"])
                        elif chunk["type"]=="WordBoundary":
                            words.append({"w":chunk["text"],"t":chunk["offset"]/10000000,"d":chunk["duration"]/10000000})
                out.with_suffix(".words.json").write_text(json.dumps(words,ensure_ascii=False), encoding="utf-8")
            try:
                asyncio.run(stream())
            except Exception:
                raise ProviderError("Edge TTS failed. Check network and voice; re-run explicitly.") from None
        duration = probe_duration(self._run, out)
        return {"duration_s": duration,
                "words_path": subs if subs.exists() else None}
