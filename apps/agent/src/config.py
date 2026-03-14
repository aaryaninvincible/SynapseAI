from functools import lru_cache
from os import getenv

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.google_api_key = getenv("GOOGLE_API_KEY", "").strip()
        self.gemini_live_model = getenv("GEMINI_LIVE_MODEL", "gemini-2.0-flash-live-001").strip()
        self.gemini_fallback_model = getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash").strip()
        raw_origins = getenv("ALLOWED_ORIGINS", "*")
        self.allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
        self.gcp_project_id = getenv("GCP_PROJECT_ID", "").strip()
        self.gcs_bucket_name = getenv("GCS_BUCKET_NAME", "").strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
