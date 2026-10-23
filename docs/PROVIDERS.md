# Providers and usage costs

## Scripts and images: Codex by default

Sign in with `codex login` using your own ChatGPT account. The official CLI handles authentication; the pipeline does not copy login files or extract tokens. The selected model uses your CLI/account default unless you set `script.model`. Image generation uses Codex's native `image_generation` feature. Size and quality are requests to the model; output is normalized to 16:9. Availability depends on your CLI version, account access, network, and quota. If the image tool is unavailable, the pipeline stops without switching to a paid API.

Successful images are cached by identity (job/prompt/refs/provider/size/quality) plus PNG hash: resuming after a failure reuses finished images without re-emitting them, and a changed job or prompt regenerates. The attempt budget is the number of concepts plus the `images.reserve_regen` allowance (default 8), always clamped to at most 36 image calls per video (72 for the two authorized runs): `reserve_regen` can only consume quota inside the cap, never above it. The pipeline runs a measured-voice preflight (300-360s required for 5-6 min targets) and an image pre-spend estimate with the effective reserve BEFORE stills and fails closed before spending quota when the script exceeds the cap, when one run would break the two-run budget, or when previously consumed calls (durable ledger `STICKMAN_BUDGET_LEDGER` or `.stickman/image_budget.json`, atomic and race-free) plus this video would exceed 72 — with no implicit Codex retries. Every attempt (successful or failed) counts before execution. See the [official authentication](https://developers.openai.com/codex/auth) and [noninteractive execution](https://developers.openai.com/codex/noninteractive) documentation.

## Narration: Edge TTS by default

Edge TTS uses a community Python package and an online Microsoft Edge service. No Edge browser or API key is required. It is not an offline engine or an official service level guarantee. The default English voice is `en-US-AndrewNeural`.

```text
stickman config set voice.provider edge
stickman config set voice.name en-US-AndrewNeural
stickman config set voice.speed 1.0
```

Script language and voice are configured separately. Spanish remains available through `project.language=es` and a Spanish voice if you choose it.

## ElevenLabs and HTTP voice

For ElevenLabs, set `ELEVENLABS_API_KEY` in your environment, then choose `voice.provider=elevenlabs`, set `voice.name` to your own voice ID, and set `align.mode=whisper-local`. Install the `[align]` extra. Voice access and API costs belong to your account.

`voice.provider=http` expects an HTTPS endpoint compatible with OpenAI's audio/speech request shape: POST `{model,input,voice,speed,response_format:"mp3"}` with Bearer authorization and a binary audio response. Set `voice.endpoint`, `voice.model`, `voice.name`, `voice.key_env`, and `align.mode=whisper-local`. Other API shapes require an adapter.

## Optional image API

`images.provider=openai-api` uses your own `OPENAI_API_KEY` and separate API billing. It is an explicit choice, independent of ChatGPT sign in. Local rendering uses your machine; remote scripts, images, and voices may use provider quota. Check the concept count in `stills/bundle/mapping.json` before scaling up.
