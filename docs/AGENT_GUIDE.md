# Guide for installing with a coding assistant

Read README, QUICKSTART, and docs/PROVIDERS before running the kit. The product generates local videos from topics; messaging review and publishing require separate integrations.

Check Python, FFmpeg, and Codex, install the package, and run `stickman check`. Ask the user to complete `codex login` when needed. Never request that they paste a token into chat or copy another person's authentication files.

The offline demo can verify rendering without remote generation. Use `--live` only when the user authorizes provider usage and quota. Do not switch to a paid provider silently. Configure language, topic, duration, and voice to the user's brief. Add brand assets only if provided. Resume from the manifest before regenerating costly stages.

Keep credentials, personal files, sessions, and runtime history out of shared ZIP files. Review the final video and report before delivery. A rendered video is not automatically published.
