# What this pipeline does

Codex Stickman Pipeline turns one English topic into a narrated 16:9 MP4.

Default path, in order:

1. Codex writes a structured script from your topic.
2. The pipeline splits that script into visual concepts, about one image every 12 seconds.
3. Codex generates the missing images in one batched call, not one call per image.
4. A voice provider reads the script. Edge TTS is the default and needs no API key.
5. Local alignment maps words to time.
6. FFmpeg builds a 1920x1080 master with camera motion, overlays, sound effects, and optional background music.
7. The pipeline writes a 480p copy, a thumbnail, a caption, and a technical report.

A stickman is optional. Object, diagram, and landscape shots should not include a person unless the script asks for one.

The pipeline does not publish videos and uses your own ChatGPT sign-in and API keys; it ships no credentials.
