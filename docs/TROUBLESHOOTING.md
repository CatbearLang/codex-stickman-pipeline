# Troubleshooting

- **PowerShell blocks activation:** run `.\.venv\Scripts\python.exe -m stickman` and `.\.venv\Scripts\python.exe -m pip` directly. No execution policy change is needed.
- **A command is not found:** reopen PowerShell after installation and confirm `ffmpeg`, `ffprobe`, `node`, `npm`, and `codex` are on PATH.
- **Codex sign in is missing:** run `codex login` and choose ChatGPT sign in. Do not paste tokens into scripts.
- **Codex does not recognize an option:** update the official CLI and inspect `codex exec --help` and `codex features list`.
- **No generated image:** check `image_generation` access, quota, and network. The kit stops without switching providers.
- **Script is rejected as too short or sparse:** retry the script stage or provide a complete local script. For the 5.5 minute default (5-6 minute standard), aim for 725-870 spoken words measured (300-360s) and one visual concept per 6-12 seconds (at most 36 images, 72 for two runs, no implicit retries).
- **Edge TTS fails:** test `edge-tts --list-voices`, your voice name, and network access.
- **Whisper starts slowly:** the optional local model may need to download first; install the `[align]` extra.
- **Concept timing is wrong:** ensure each `narration_span` exactly follows the scene voiceover. Use Whisper when a voice provider has no word boundaries.
- **Image attempt limit reached:** inspect `attempts` in the stills manifest (`stills/work/manifest.json`). The attempt budget is concepts plus `images.reserve_regen` (default 8), always clamped to at most 36 calls per video: raising the reserve only consumes quota inside the cap, never above it. Every attempt counts, including failed ones; resume with the same command to reuse finished images without re-emitting them. There are no automatic retries — a failure aborts and you resume manually.
- **An interrupted run:** use `stickman resume --live` for bank jobs, or repeat the same `--topic` command for an individual job. Keep the project state for recovery.

For support, share your OS, versions, selected providers, and a concise error message. Never share authentication files, environment secrets, or full Codex logs.
