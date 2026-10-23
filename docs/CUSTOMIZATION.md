# Customization

## Brief for your assistant or team

> I want documentaries about [NICHE] for [AUDIENCE], in [LANGUAGE], around [MINUTES] minutes long. The tone is [TONE]. Use [VOICE PROVIDER/ID]. Visual references are in [FOLDER], and licensed assets are in [FOLDER]. Keep each visual concept aligned to its narration. Do not add an intro or publish anything unless I request it. Explain provider requirements and costs before changing providers. Never place my credentials in distributable files.

## Included assets and music

Inter and League Spartan fonts are included under the Open Font License. Original pop and whoosh effects are included. The default background is "Accralate" by Kevin MacLeod (CC BY 4.0, see THIRD_PARTY_NOTICES.md); it plays with ducking under the narration at `render.bgm=accralate` and its credit is appended automatically to `caption.txt`. Use `stickman config set render.bgm none` to turn music off, `bundled` (or `ambient`) for the procedural bed, or set `render.bgm` to the path of your own licensed track and adjust `render.bgm_volume`. Keep any required attribution.

## Script, language, and duration

The default `project.language` is `en`, and `project.target_minutes` is 5.5 (5-6 minute standard; valid range 0.1-60). The generated script must meet its word and image density checks before media generation (725-870 words (300-360s measured) and ~30-36 visual concepts for the default, hard cap 36 per video and 72 for two runs). Target duration is editorial; the render follows the actual voice recording. Voice selection is separate from script language. For a custom script, use `stickman init project --from-script path.json`, following `examples/script.json`. Concept `narration_span` values must cover each scene's voiceover exactly, in order, with unique IDs.

Edge word boundaries or local Whisper can provide measured timing. `align.mode=proportional` spreads words evenly as an approximation.

## Visual style

Edit `src/stickman/scriptx/style.py` for the white, dark line, muted prop, and selective yellow preset. Overlay text is added after images are generated. Edit `render/overlays.py` and `render/composer.py` for layout and composition. The preset does not guarantee recurring character identity. A vertical format requires new safe areas, framing, overlays, thumbnails, and tests; swapping width and height is insufficient.

Bring your own topic bank, verified research, voice rights, music rights, logos, licensed fonts, and brand rules for a more specific channel.
