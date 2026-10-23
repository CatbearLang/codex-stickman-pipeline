"""User-owned voice providers."""
def make_voice_provider(cfg):
    c = cfg.get("voice", {})
    name = c.get("provider", "edge")
    if name == "edge":
        from .edge import EdgeVoice
        return EdgeVoice()
    if name == "elevenlabs":
        from .elevenlabs import ElevenLabsVoice
        return ElevenLabsVoice(model=c.get("model") or "eleven_multilingual_v2")
    if name == "http":
        from .http import HttpVoice
        return HttpVoice(endpoint=c.get("endpoint", ""), key_env=c.get("key_env", "TTS_API_KEY"), model=c.get("model", ""))
    raise ValueError("Unsupported voice provider")
