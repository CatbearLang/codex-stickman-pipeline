# How it was built

🇪🇸 [Español](HOW_IT_WAS_BUILT.es.md)

This document explains **why** Codex Stickman Pipeline exists, **how** each stage works and the engineering decisions behind it. For the module map see [ARCHITECTURE.md](ARCHITECTURE.md).

## The problem

Explainer videos ("stickman" / whiteboard style) are slow to make by hand: write a script, record a voice, draw or generate one image every few seconds, sync everything and edit. Most of that is repeatable. The goal was a **single command** — `stickman run` — that turns a topic into a finished 1080p MP4 with a thumbnail and caption, while keeping cost predictable and every run reproducible.

## Stage by stage

| Stage | Input → Output | Key idea |
|---|---|---|
| **Topic bank** | `topics` file → next topic | Exclusive OS lock + job journal: a crashed run resumes the same topic instead of consuming a new one |
| **Script** | topic → JSON script (scenes → visual concepts) | LLM output validated against `script-schema.json`; quality gates check pacing, word budget and image density **before** any paid call |
| **Voice** | script → per-scene audio | Edge TTS by default (no key); ElevenLabs or any HTTP TTS behind the same interface; measured-duration preflight |
| **Align** | audio → word timestamps | Edge word boundaries or local faster-whisper; `timeline.py` maps each concept to a time range (~1 image / 12 s) |
| **Stills** | concepts → images | One batched generation call; durable budget ledger; cache key = job + prompt + refs + provider + size + quality, plus PNG hash |
| **Compose** | images + audio → MP4 | FFmpeg filter graph: camera motion, crossfades, overlays, procedural SFX, background music with ducking, loudness normalization |
| **Verify** | MP4 → report | ffprobe checks (streams, duration, loudness) written to `technical-check.json`; 480p copy and thumbnail |

## Design decisions

1. **Fail closed on cost.** Nothing paid runs without `--live`. Providers are chosen explicitly — no silent fallback to a paid API. Image calls are estimated and counted against a ledger *before* they run, so two runs cannot overspend together.
2. **Small provider interfaces.** Script, voice and image providers sit behind `provider_base.py` / factories. Adding a service is one class; tests swap in doubles.
3. **Idempotent, resumable stages.** Content hashes and a manifest let a re-run reuse finished work after a crash or a tweak.
4. **No credential handling.** Codex authentication stays inside the official CLI; API keys come only from environment variables. A release secret scanner is part of the test suite.
5. **Offline demo path.** A procedural-image + test-tone render works with zero accounts, so anyone can verify the FFmpeg path in minutes.
6. **Own assets.** Sound effects are procedurally generated; bundled music and fonts carry their licenses in `THIRD_PARTY_NOTICES.md`.

## Testing

`pytest -q` runs fully offline with test doubles for every provider: **94 passed, 2 skipped**. Coverage includes topic-bank locking, config validation, provider contracts, script schema, pacing and budget gates (including a two-run budget race), image caching, the FFmpeg render path, output verification and the secret scanner.

## Workflow

Built in Python as a CLI-first tool, iterating with AI coding assistants: each change was specified, implemented, then checked by the test suite and by rendering real videos and inspecting the technical report. Real-run failures (overspending risk, crashes mid-job, pacing that felt too slow) became gates and tests rather than manual rules.

## What I'd do next

Vertical 9:16 output, more voice/image providers and a small web dashboard — see the Roadmap in the README.
