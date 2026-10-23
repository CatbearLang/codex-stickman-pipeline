# Installation

## Windows 10/11

Install Python 3.11-3.13, Node.js, and FFmpeg from their official installers. Ensure `py`, `node`, `npm`, `ffmpeg`, and `ffprobe` are available in a new PowerShell window. Clone the repository to a short writable path such as `C:\dev\codex-stickman-pipeline`; avoid a cloud synced folder while rendering.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
npm install -g @openai/codex
codex login
.\.venv\Scripts\python.exe -m stickman check
```

This direct Python path works even when PowerShell script execution blocks virtual environment activation. You can optionally activate with `.\.venv\Scripts\Activate.ps1` and then use `stickman` directly. If `codex` is missing after npm installation, reopen PowerShell and check `npm config get prefix`; the npm global command directory must be on PATH.

## macOS and Linux

Install Python 3.11+, FFmpeg/ffprobe, and Node.js. From the cloned repository folder:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
npm install -g @openai/codex
codex login
stickman check
```

## Diagnostics and optional packages

Check `python --version`, `ffmpeg -version`, `ffprobe -version`, `codex --version`, `codex login status`, and `stickman check`. FFmpeg, Node.js, and Codex are installed separately. For ElevenLabs or generic HTTP voices, install `python -m pip install -e '.[align]'` and set `align.mode` to `whisper-local`; first use may download a speech recognition model.

For development, install `python -m pip install -e '.[dev]'` and run `python -m pytest`. The unit tests require no credentials. Fonts are included in the package. To remove the package, uninstall `stickman-cli` and delete the local virtual environment separately. `codex logout` signs out of Codex.
