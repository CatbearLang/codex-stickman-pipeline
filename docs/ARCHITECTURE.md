# Architecture

## Flow

1. **CLI** (`cli.py`) parses commands and builds the pipeline from `stickman.toml` (`config.py`, validated, secret-free).
2. **Orchestration** (`flow.py`) takes an exclusive OS lock on the project for the whole run, pulls the next topic from the **topic bank** (`bank.py`), and records progress in a job **manifest/journal** (`manifest.py`). A crash releases the lock; the next run resumes the active job without consuming another topic.
3. **Pipeline** (`pipeline.py`) runs the stages:
   - `script`: `scriptx/` generates a structured JSON script (scenes → visual concepts) via the configured LLM provider, validated against `assets/script-schema.json`; `scriptx/gates.py` enforces word budget and image density *before* any spend.
   - `voice`: `voice/` synthesizes per-scene audio (Edge TTS default); `voice/preflight.py` checks measured duration.
   - `align`: word timestamps (Edge word boundaries or local faster-whisper) map concepts to time ranges (`timeline.py`).
   - `stills`: `stills/runner.py` estimates calls, checks the durable budget ledger, batches generation and caches images by (job, prompt, refs, provider, size, quality) + PNG hash.
   - `compose`: `render/composer.py` builds an FFmpeg filter graph with camera motion, crossfades, overlays (`render/overlays.py`), SFX and BGM ducking (`bgm.py`), then loudness-normalizes.
   - `verify`: `verify.py` probes the output and writes `technical-check.json`; `thumbnailx.py` builds the thumbnail.
4. Results are copied to `deliveries/<id>/`.

## Design decisions

- **Fail closed on cost**: provider calls are gated by `--live`, by explicit provider choice (no implicit fallback) and by hard image caps. Every attempt is counted before it runs.
- **Providers behind small interfaces** (`provider_base.py`, `*/base.py`, `*/factory.py`) so tests inject doubles and new services are easy to add (see `docs/EXTENSIONS.md`).
- **Idempotent stages** with content hashes so re-runs reuse work.
- **No credential handling**: Codex authentication stays inside the official CLI; API keys come only from environment variables.
