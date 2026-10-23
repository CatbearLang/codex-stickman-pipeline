"""Image provider selection. No automatic provider fallback."""
def make_image_provider(cfg):
    name = cfg.get("images", {}).get("provider", "codex-oauth")
    if name == "codex-oauth":
        from .codex_oauth import CodexOAuthImages
        return CodexOAuthImages(model=cfg.get("script", {}).get("model", ""))
    if name == "openai-api":
        from .openai_api import OpenAIImages
        return OpenAIImages()
    raise ValueError("Unsupported image provider")
