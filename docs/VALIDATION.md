# Validation record

Updated September 22, 2026. Release version 1.0.1.

## Checks performed

- 70 automated tests passed on native Windows with `python -m pytest -q`. Coverage includes topic bank locking, configuration, provider contracts, script structure, measured duration, concept timing, image caching, offline integration, and ZIP scanner behavior.
- An offline FFmpeg demo runs without remote services and checks video output, bundled fonts, sound, crossfades, and thumbnail generation.
- Project scripts, captions, metadata, and intermediate JSON now use explicit UTF-8 reads and writes for Windows locale independence.
- A generated 5.5 minute script (5-6 minute standard) is rejected before voice and image generation if it misses the 5-6 minute word window at 145 WPM (725-870 words measured, 300-360s) or exceeds 36 image concepts or has fewer than roughly one image per 12 seconds (~30-36 images). Measured voice duration is checked again before image generation.
- The release ZIP uses an exact allowlist and checks file hashes, CRC, credential names, private paths, and symlinks. It excludes development environments and previous project output.

## Limits

The offline demo uses procedural test images and tones. It is not a sample of remote AI quality or final narration. Codex image generation, ChatGPT quota, Edge TTS availability, and optional paid providers depend on the user's account and network. Editorial accuracy still requires a human review. The included short example is a workflow sample; it does not represent the new 5.5 minute default.
