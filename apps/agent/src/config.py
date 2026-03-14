from functools import lru_cache
from os import getenv


class Settings:
    def __init__(self) -> None:
        self.google_api_key = getenv("GOOGLE_API_KEY", "").strip()
        raw_origins = getenv("ALLOWED_ORIGINS", "*")
        self.allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

