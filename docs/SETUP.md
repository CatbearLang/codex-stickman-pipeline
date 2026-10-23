# Setup

## 1. Install the tools

Install Python 3.11-3.13, Node.js, and FFmpeg from their official sites. Open a new terminal and confirm:

```text
python --version
node --version
ffmpeg -version
ffprobe -version
```

On Windows, `py -3.11` can replace `python`.

## 2. Install this kit

Clone the repository to a short local path, such as `C:\dev\codex-stickman-pipeline`. Avoid a cloud-synced folder while rendering.

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
npm install -g @openai/codex
codex login
.\.venv\Scripts\python.exe -m stickman check
```

macOS or Linux:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
npm install -g @openai/codex
codex login
stickman check
```

`codex login` uses your ChatGPT account. This kit never copies that login.

## 3. Make the first video

```text
stickman init "My Channel" --topic "How a paper airplane glides"
stickman run --project "My Channel" --live
```

`--live` is what allows Codex and the voice service to run. Without it, the pipeline stops before remote calls.

The finished file is:

```text
My Channel/deliveries/<id>/master.mp4
```

## 4. Choose a voice

Edge TTS is already the default. To set it explicitly:

```text
stickman config set voice.provider edge
stickman config set voice.name en-US-AndrewNeural
stickman config set voice.speed 1.0
```

ElevenLabs, using your own key and voice ID:

```text
python -m pip install -e ".[align]"
stickman config set voice.provider elevenlabs
stickman config set voice.name YOUR_ELEVENLABS_VOICE_ID
stickman config set align.mode whisper-local
```

Then set `ELEVENLABS_API_KEY` in the environment before `stickman run --live`.

Your own HTTPS speech endpoint, if it matches OpenAI's audio/speech shape:

```text
python -m pip install -e ".[align]"
stickman config set voice.provider http
stickman config set voice.endpoint https://example.com/v1/audio/speech
stickman config set voice.model your-model
stickman config set voice.name your-voice
stickman config set voice.key_env TTS_API_KEY
stickman config set align.mode whisper-local
```

Set the named environment variable before the run. Other API shapes need a small adapter in `src/stickman/voice/`.

## 5. Check the result

`stickman check` should pass before a real run. A completed delivery also includes `technical-check.json`. Review the video yourself before publishing. This kit does not upload anywhere.
