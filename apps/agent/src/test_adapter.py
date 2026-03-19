import asyncio
from .gemini_live import GeminiLiveAdapter
from .config import get_settings

async def test():
    settings = get_settings()
    a = GeminiLiveAdapter(
        settings.google_api_keys,
        settings.openrouter_api_key,
        settings.anthropic_api_key,
        settings.sarvam_api_key,
        settings.gemini_live_model,
        settings.gemini_fallback_model,
        settings.default_provider,
        settings.default_model,
    )
    print("api key loaded: ", bool(settings.google_api_keys), "client ready:", a._client is not None, a.fallback_model)
    r = await a.generate("123", "write python code for printing hello world")
    print(r.spoken_text)

if __name__ == "__main__":
    asyncio.run(test())
