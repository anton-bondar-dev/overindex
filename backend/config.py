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

    # LLM (Gemini): a key POOL (rotate on quota) + a MODEL fallback chain.
    gemini_api_key: str = ""            # single key (fallback)
    gemini_api_keys: str = ""           # comma-separated POOL (one per Google account)
    # Models tried in order; on 503/overload we move to the next. "lite-latest" is
    # ~0.5s and far less overloaded than the full flash models (which 503 heavily).
    gemini_models: str = "gemini-flash-lite-latest,gemini-3.8-flash"
    gemini_model: str = "gemini-flash-lite-latest"   # primary (shown in healthz)
    gemini_thinking_budget: int = 0     # applied ONLY to non-lite "thinking" models

    # Groq (OpenAI-compatible) — PRIMARY provider. Fast from any IP (Gemini is
    # heavily throttled from the datacenter host), strong tool-calling (Llama tops
    # the Berkeley function-calling leaderboard). Free tier is per-account.
    llm_provider: str = "groq"          # "groq" | "gemini"
    groq_api_key: str = ""              # single key
    groq_api_keys: str = ""             # comma-separated pool (rotate on 429)
    groq_models: str = "llama-3.3-70b-versatile,llama-3.1-8b-instant"

    # Limits — protect the Qloo monthly budget AND the Gemini daily quota
    max_qloo_concurrency: int = 5          # parallel in-flight Qloo calls
    per_ip_per_min: int = 10               # novel (non-cached) runs per IP / minute
    daily_fresh_run_cap: int = 200         # novel LLM-hitting runs per day, total
    max_live_runs: int = 6                 # max concurrent live (non-cached) runs
    run_deadline_s: int = 90               # hard wall-clock cap on a single live run
    cache_ttl_days: int = 7
    run_grace_s: int = 300                 # keep a finished run fetchable this long, then evict

    # Deploy
    public_base_url: str = "https://overindex.overpro.fit"
    # Default to the demo origin, NOT "*" — the frontend is same-origin anyway, so
    # a wildcard only lets any site drive quota-spending runs from a visitor's browser.
    allowed_origins: str = "https://overindex.overpro.fit"

    def gemini_key_pool(self) -> list[str]:
        """All Gemini keys to rotate across (pool first, else the single key)."""
        pool = [k.strip() for k in self.gemini_api_keys.split(",") if k.strip()]
        if not pool and self.gemini_api_key:
            pool = [self.gemini_api_key]
        return pool

    def gemini_model_chain(self) -> list[str]:
        """Models to try in order (fall through on 503/overload)."""
        chain = [m.strip() for m in self.gemini_models.split(",") if m.strip()]
        return chain or [self.gemini_model]

    def groq_key_pool(self) -> list[str]:
        """All Groq keys to rotate across (pool first, else the single key)."""
        pool = [k.strip() for k in self.groq_api_keys.split(",") if k.strip()]
        if not pool and self.groq_api_key:
            pool = [self.groq_api_key]
        return pool

    def groq_model_chain(self) -> list[str]:
        """Groq models to try in order (fall through on error/overload)."""
        chain = [m.strip() for m in self.groq_models.split(",") if m.strip()]
        return chain or ["llama-3.3-70b-versatile"]


settings = Settings()
