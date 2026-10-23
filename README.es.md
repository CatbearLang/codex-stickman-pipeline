# 🎬 Codex Stickman Pipeline (Español)

**Escribís un tema y obtenés un video explicativo narrado con personajes stickman (MP4 1080p).**

CLI en Python, de punta a punta y reanudable, que orquesta la escritura del guion con un LLM, la generación de imágenes con IA, la voz (TTS), la sincronización palabra por palabra y el render con FFmpeg. Incluye controles de presupuesto, caché y tests.

## Puntos clave

- Pipeline por etapas (`script → voice → align → stills → compose → verify`), cada etapa se puede volver a ejecutar sola.
- Proveedores intercambiables: Codex CLI (con tu cuenta de ChatGPT), OpenAI Images, cualquier LLM HTTP compatible con OpenAI, Edge TTS, ElevenLabs y Whisper local.
- Control de costos: límite de imágenes por video, estimación antes de gastar, registro de presupuesto persistente y nunca cambia a un proveedor pago sin avisar. Las llamadas remotas requieren `--live`.
- Reanudable y seguro ante concurrencia: banco de temas con locks del sistema operativo, journal de trabajos y caché de imágenes por hash.
- Render profesional: 1920×1080 a 30 fps, movimiento de cámara, transiciones, efectos, música con ducking y normalización a −14 LUFS.

## Inicio rápido

```bash
pip install -e ".[dev]"
python tools/demo.py --out demo-local          # demo offline, sin cuentas
codex login && stickman check
stickman init "Mi Canal" --topic "Cómo planea un avión de papel"
stickman config set project.language es
stickman run --project "Mi Canal" --live
```

Tests: `pytest -q` (offline). Documentación completa en inglés: [README.md](README.md).

Licencia MIT · Autor: **Lian Yang**, Ingeniero en Informática · [@CatbearLang](https://github.com/CatbearLang)
