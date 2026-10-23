"""Interfaz ImageProvider (§4.3): generate -> {bytes, sha256, w, h}."""
from __future__ import annotations

from pathlib import Path

from stickman.provider_base import Provider


class ImageProvider(Provider):
    def generate(self, prompt: str, out: Path, *, size: str, quality: str,
                 refs: list[Path]) -> dict:
        raise NotImplementedError
