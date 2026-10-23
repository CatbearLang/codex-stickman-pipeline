# Your first video

## 1. Requirements

Python 3.11-3.13, Node.js, FFmpeg and ffprobe on PATH, and the official `@openai/codex` CLI. You need your own ChatGPT account with Codex and image generation access. Edge TTS also needs internet. A GPU is not required for the default render. Allow at least 10 GB of free disk space for initial use.

## 2. Install on Windows

Open PowerShell in the cloned repository folder. Run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
npm install -g @openai/codex
codex login
stickman check
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe -m pip install -e .` and `.\.venv\Scripts\python.exe -m stickman` in place of `python` and `stickman`; no policy change is required. Open a new terminal after installing FFmpeg or Node.js so PATH refreshes. See [INSTALL](docs/INSTALL.md) for macOS/Linux and more Windows details.

## 3. Run the offline demo

```powershell
python tools/demo.py --out demo-local
```

This tests rendering with local geometric images and test tones. It does not represent AI image quality or synthetic speech quality and does not call external services.

## 4. Make a real video

```powershell
stickman init "First Video" --topic "How a paper airplane glides"
stickman run --project "First Video" --live
```

`--live` permits the configured providers to use your account and quota. Without it, generation stops before remote calls. Review `First Video/deliveries/<id>/master.mp4` and `technical-check.json`. No video is published automatically.

## 5. Topics and resume

Edit `First Video/banco tema.txt`, one English topic per line. Run `stickman run --project "First Video" --live` for the next topic, or add `--batch 3` for up to three. If a batch fails, run `stickman resume --project "First Video" --live`. For a topic outside the bank, use `stickman run --project "First Video" --topic "Your idea" --live` and repeat that exact command if it fails.

The 5.5 minute default (5-6 minute standard) typically calls for ~30-36 distinct images (hard cap 36 per video, 72 for two runs). The generated script is rejected before voice or images if it is too short or has too few concepts. Review costs and quotas before a full run.
