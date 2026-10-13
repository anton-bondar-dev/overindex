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

    # LLM — Groq (OpenAI-compatible chat/completions). Fast from any IP and strong at
    # tool-calling; free tier is per-account. The key pool rotates on 429, the model
    # chain falls through on overload.
    groq_api_key: str = ""              # single key
    groq_api_keys: str = ""             # comma-separated pool (rotate on 429)
    groq_models: str = "openai/gpt-oss-120b,openai/gpt-oss-20b"

    # Limits — protect the Qloo budget AND the Groq free-tier (8k tokens/min) quota
    max_qloo_concurrency: int = 5          # parallel in-flight Qloo calls
    per_ip_per_min: int = 10               # novel (non-cached) runs per IP / minute
    daily_fresh_run_cap: int = 200         # novel LLM-hitting runs per day, total
    max_live_runs: int = 6                 # max concurrent live (non-cached) runs
    max_total_runs: int = 400              # hard cap on the run registry (cached + live)
    run_deadline_s: int = 90               # hard wall-clock cap on a single live run
    run_grace_s: int = 300                 # keep a finished run fetchable this long, then evict

    # Deploy
    public_base_url: str = "https://overindex.overpro.fit"
    # Default to the demo origin, NOT "*" — the frontend is same-origin anyway, so
    # a wildcard only lets any site drive quota-spending runs from a visitor's browser.
    allowed_origins: str = "https://overindex.overpro.fit"

    def groq_key_pool(self) -> list[str]:
        """All Groq keys to rotate across (pool first, else the single key)."""
        pool = [k.strip() for k in self.groq_api_keys.split(",") if k.strip()]
        if not pool and self.groq_api_key:
            pool = [self.groq_api_key]
        return pool

    def groq_model_chain(self) -> list[str]:
        """Groq models to try in order (fall through on error/overload)."""
        chain = [m.strip() for m in self.groq_models.split(",") if m.strip()]
        return chain or ["openai/gpt-oss-120b"]


settings = Settings()
