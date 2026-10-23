"""Native Codex image generation. No token extraction or private endpoints."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
import tempfile
from PIL import Image
from stickman.codex_cli import execute, check_login
from stickman.errors import ProviderError
from stickman.provider_base import Requirement
from .base import ImageProvider
from .runner import sha256_file


def _codex_generated_images_root() -> Path:
    home = os.environ.get("CODEX_HOME")
    base = Path(home) if home else Path.home() / ".codex"
    return base / "generated_images"


def _snapshot_generated_images() -> dict[str, int]:
    root = _codex_generated_images_root()
    snap: dict[str, int] = {}
    if not root.is_dir():
        return snap
    try:
        for p in root.rglob("*.png"):
            try:
                snap[str(p)] = p.stat().st_mtime_ns
            except OSError:
                continue
    except OSError:
        pass
    return snap


def _new_generated_images(before: dict[str, int]) -> list[Path]:
    root = _codex_generated_images_root()
    if not root.is_dir():
        return []
    found: list[tuple[int, Path]] = []
    try:
        for p in root.rglob("*.png"):
            try:
                st = p.stat()
            except OSError:
                continue
            key = str(p)
            if key not in before or st.st_mtime_ns != before[key]:
                found.append((st.st_mtime_ns, p))
    except OSError:
        return []
    found.sort()
    return [p for _, p in found]


class CodexOAuthImages(ImageProvider):
    name = "codex-oauth"
    verified = False

    def __init__(self, *, model="", **kwargs):
        self.model = model

    def requirements(self):
        return [Requirement(kind="login", label="Codex CLI ChatGPT login and native image_generation tool")]

    def check(self):
        ok, hint = check_login()
        return {"ok": ok, "hint": hint, "details": {"requirements": []}}

    def generate(self, prompt, out, *, size, quality, refs):
        if refs:
            raise ProviderError("Reference images require a custom provider; this preset is text-to-image.")
        name = Path(out).name
        reports = self.generate_batch(
            [{"filename": name, "prompt": prompt}], Path(out).parent, size=size, quality=quality)
        return reports[name]

    def generate_batch(self, items, directory, *, size, quality):
        """One Codex exec for N independent images. items: [{filename, prompt}]."""
        if not items:
            return {}
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        blocks = []
        for i, item in enumerate(items, 1):
            name = Path(item["filename"]).name
            if Path(name).name != name or not name.endswith(".png"):
                raise ProviderError("Image filename must be a local PNG basename")
            blocks.append(
                "IMAGE %d — save exactly as %s\nIndependent scene. Do not continue another image.\n%s"
                % (i, name, item.get("prompt", "")))
        request = (
            "Use the native image generation tool to generate exactly %d separate, independent images in this one response. "
            "Do not draw them with Python, SVG, HTML or another substitute. "
            "Each image: fully opaque warm off-white or muted colored background, never transparent; "
            "preserve soft shadows and simple layered scenery described in each prompt. "
            "Save each PNG under the exact filename given. No other files are needed. "
            "If the image tool is unavailable, stop and say so. "
            "Requested canvas %s, quality %s; use closest native supported setting.\n\n%s"
            % (len(items), size, quality, "\n\n---\n\n".join(blocks)))
        with tempfile.TemporaryDirectory(prefix="stickman-image-batch-") as d:
            before = _snapshot_generated_images()
            execute(request, d, model=self.model, image=True,
                    timeout=max(900, 300 + 60 * len(items)))
            work = Path(d)
            recovered = _new_generated_images(before)
            out = {}
            for i, item in enumerate(items):
                name = Path(item["filename"]).name
                src = work / name
                if not src.exists() or src.stat().st_size <= 0:
                    alt = work / "image.png"
                    if alt.exists() and alt.stat().st_size > 0 and len(items) == 1:
                        src = alt
                if (not src.exists() or src.stat().st_size <= 0) and i < len(recovered):
                    try:
                        shutil.copyfile(recovered[i], src)
                    except OSError:
                        pass
                if not src.exists() or src.stat().st_size <= 0:
                    raise ProviderError(
                        "Codex produced no %s. Check native image_generation availability for this account. No paid API fallback occurred."
                        % name)
                dest = directory / name
                with Image.open(src) as im:
                    im.verify()
                with Image.open(src) as im:
                    rgba = im.convert("RGBA")
                    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                    Image.alpha_composite(background, rgba).convert("RGB").save(dest, "PNG")
                with Image.open(dest) as im:
                    w, h = im.size
                out[name] = {"width": w, "height": h, "bytes": dest.stat().st_size, "sha256": sha256_file(dest)}
            return out
