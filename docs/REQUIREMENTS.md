# Requirements

You need all of these before a real video:

- Windows 10/11, macOS, or Linux.
- Python 3.11, 3.12, or 3.13.
- Node.js and npm, only to install the official Codex CLI.
- FFmpeg and ffprobe on PATH.
- Internet access.
- Your own ChatGPT account, signed in with `codex login`, with script and image generation available.
- About 10 GB of free disk space for a first full video and its working files.

Default voice:

- Edge TTS. No API key. It uses an online Microsoft Edge speech service through the `edge-tts` package. It is not an offline engine and not an official uptime guarantee.
- Default English voice: `en-US-AndrewNeural`.

Optional, only if you change the voice:

- ElevenLabs: your own `ELEVENLABS_API_KEY` and a voice ID. Paid by your ElevenLabs account.
- Any HTTPS speech endpoint that accepts an OpenAI-style audio request and returns MP3 bytes.
- For those two options, also install the `[align]` extra. The first alignment run may download a local speech model.

Not required:

- A GPU.
- An OpenAI API key, unless you explicitly switch images to `openai-api`.
- A browser login inside this pipeline. Codex keeps its own login.
