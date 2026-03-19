from functools import lru_cache
from os import getenv

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        raw_keys = getenv("GOOGLE_API_KEY", "")
        self.google_api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
        self.gemini_live_model = getenv("GEMINI_LIVE_MODEL", "gemini-2.0-flash-live-001").strip()
        self.gemini_fallback_model = getenv("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash").strip()
        self.openrouter_api_key = getenv("OPENROUTER_API_KEY", "").strip()
        self.anthropic_api_key = getenv("ANTHROPIC_API_KEY", "").strip()
        self.sarvam_api_key = getenv("SARVAM_API_KEY", "").strip()
        self.default_provider = getenv("DEFAULT_LLM_PROVIDER", "gemini").strip().lower()
        self.default_model = getenv("DEFAULT_LLM_MODEL", "").strip()
        raw_origins = getenv("ALLOWED_ORIGINS", "*")
        self.allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
        self.gcp_project_id = getenv("GCP_PROJECT_ID", "").strip()
        self.gcs_bucket_name = getenv("GCS_BUCKET_NAME", "").strip()
        self.browser_cdp_url = getenv("BROWSER_CDP_URL", "").strip()
        self.browser_headless = getenv("BROWSER_HEADLESS", "true").strip().lower() != "false"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
