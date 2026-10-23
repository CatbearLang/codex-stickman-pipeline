"""stickman/thumbnailx.py — miniatura adicional (plan F8).

make_thumbnail(src=..., out=..., hook=...): `src` (--from-image) es
OBLIGATORIO y debe ser una imagen original (still del proyecto); NUNCA
se extrae un frame del máster (error explícito si src apunta a un mp4).
Escalado cover-crop a 1280x720 con Pillow (jamás stretch) + hook opcional
dibujado con Pillow (sin fuentes privadas: usa la default de Pillow).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

TW, TH_ = 1280, 720


def make_thumbnail(*, src: str | Path | None, out: str | Path,
                   hook: str = "") -> Path:
    if src is None:
        raise ValueError(
            "thumbnail exige --from-image (still original); "
            "no se extrae frame del máster")
    p = Path(src)
    if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError(
            f"--from-image debe ser una imagen original (still), no {p!r}; "
            "extraer del máster está prohibido (calidad/scratch)")
    if not p.exists():
        raise ValueError(f"--from-image no existe: {p}")
    img = Image.open(p).convert("RGB")
    # cover-crop 16:9 centrado (jamás stretch)
    w, h = img.size
    ratio = w / h
    if ratio > TW / TH_:
        nw, nh = int(round(h * TW / TH_)), h
    else:
        nw, nh = w, int(round(w * TH_ / TW))
    left, top = (w - nw) // 2, (h - nh) // 2
    img = img.crop((left, top, left + nw, top + nh)).resize(
        (TW, TH_), Image.Resampling.LANCZOS)
    if hook:
        from PIL import ImageDraw, ImageFont
        text = " ".join(hook.upper().split()[:5])
        font_path=Path(__file__).resolve().parent/"assets/fonts/LeagueSpartan-Variable.ttf"
        d=ImageDraw.Draw(img)
        size=84
        while size>24:
            font=ImageFont.truetype(str(font_path),size)
            font.set_variation_by_axes([700])
            if d.textbbox((0,0),text,font=font)[2] < TW-100:break
            size-=2
        d.rounded_rectangle((24,20,TW-24,148),radius=20,fill="#F2C94C")
        box=d.textbbox((0,0),text,font=font)
        d.text(((TW-(box[2]-box[0]))/2,78-(box[3]+box[1])/2),text,font=font,fill="#1A1A1A")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    return out
