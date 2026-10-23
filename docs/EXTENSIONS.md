# Optional review and publishing integrations

The kit ends at `deliveries/<id>/metadata.json`, with `status: rendered` and `published: false`. It has no WhatsApp client, social account credentials, approval timer, or automatic publishing.

A separate integration can watch completed deliveries, record the video ID and hash to prevent duplicates, send a copy or link through an authorized channel, record an explicit approval, publish with the platform's own OAuth/API, and retain its remote ID and URL. A timeout means approval is still pending. Check the platform before retrying an ambiguous upload.

Keep integration code and secrets outside a distributable kit. Technical verification checks the file, audio, and duration; it does not replace editorial review. To schedule a local run, invoke `stickman run --project PATH --live` with your operating system scheduler after setup. The kit installs no schedule by default. A project lock prevents concurrent runs in the same folder.
