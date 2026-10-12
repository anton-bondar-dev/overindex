"""Runtime configuration (pydantic-settings).

Reads from environment / .env. Nothing secret is hard-coded. Set USE_MOCK_QLOO=1
to develop the whole pipeline before the real Qloo key arrives.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Qloo
    qloo_api_key: str = ""
    qloo_base_url: str = "https://hackathon.api.qloo.com"
    use_mock_qloo: bool = False  # build/test the pipeline with no key

    # LLM (Gemini primary; Groq is a fallback seam, not shipped yet)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    groq_api_key: str = ""

    # Limits — protect the Qloo monthly budget AND the Gemini daily quota
    max_qloo_concurrency: int = 5          # parallel in-flight Qloo calls
    per_ip_per_min: int = 10               # novel (non-cached) runs per IP / minute
    daily_fresh_run_cap: int = 200         # novel LLM-hitting runs per day, total
    cache_ttl_days: int = 7

    # Deploy
    public_base_url: str = "https://overindex.overpro.fit"
    allowed_origins: str = "*"             # tighten to the demo origin for prod


settings = Settings()
