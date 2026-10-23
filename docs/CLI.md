# Command reference

Run `stickman --help` or `stickman COMMAND --help`. Quote paths containing spaces.

| Command | Purpose |
|---|---|
| `stickman init project --topic "Idea"` | Create a project and add its first topic |
| `stickman init project --from-script script.json` | Start with a validated local script |
| `stickman check` | Check local dependencies and Codex sign in |
| `stickman config show` | Show project settings |
| `stickman config set project.target_minutes 5.5` | Change the target length |
| `stickman script validate script.json` | Validate script IDs and narration spans |
| `stickman run --project project --live` | Produce the next topic from the bank |
| `stickman run --project project --topic "Idea" --live` | Produce one topic without changing the bank |
| `stickman run --project project --batch 3 --live` | Produce up to three topics |
| `stickman resume --project project --live` | Resume an interrupted bank job |
| `stickman status --project project --json` | Read job status as JSON |
| `stickman run --project project --stage voice --live` | Regenerate scene voice files |
| `stickman run --project project --stage align` | Align words |
| `stickman run --project project --stage compose` | Render with existing assets |
| `stickman run --project project --stage verify` | Check the video file |
| `stickman thumbnail --from-image image.png --hook "Title" --out thumb.png` | Create a thumbnail |

Manual stages are `script`, `voice`, `align`, `stills`, `compose`, and `verify`. Manual stages can overwrite derived files; use the full pipeline to resume safely. `clean --force` deletes derived assets, but keeps completed deliveries.

Exit codes: 0 success or empty topic bank; 1 usage/configuration error; 2 missing live authorization or requirement; 3 provider/render/verification failure; 4 another process holds the project lock.

Requirements and providers: scripts and images use Codex (`codex login` with your own ChatGPT account; native `image_generation`); narration defaults to Edge TTS (online Microsoft Edge service via `edge-tts`, no key); local render needs FFmpeg/ffprobe. Optional paid providers: `images.provider=openai-api` (your `OPENAI_API_KEY`), `voice.provider=elevenlabs`/`http` (your key + `align.mode=whisper-local`). No provider fallback is ever implicit.

Call estimate before spending quota: one concept = one Codex image call; hard cap 36 calls per video and 72 for the two authorized runs. The pipeline runs a measured-voice preflight (300-360s required for 5-6 min targets) and an image pre-spend estimate with the effective `images.reserve_regen` allowance (default 8, always clamped so the total never exceeds 36) BEFORE stills, consulting the durable cross-project ledger (`STICKMAN_BUDGET_LEDGER` or `.stickman/image_budget.json`); it fails closed (exit 3, resumable) when the script exceeds the cap, when one run would break the two-run budget, or when consumed calls plus this video would exceed 72 — with no implicit Codex retries and every attempt (successful or failed) counted before execution. Check `stills/bundle/mapping.json` (`expected_images`) to confirm the count for the current job.

Defaults: 1080p, 30 fps, 0.25 second crossfades, and a -14 LUFS mix target. Validate again after changing rendering settings.
