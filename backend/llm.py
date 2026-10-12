"""Gemini LLM provider with a rotating key pool.

Talks to the REST generateContent API directly for full control over tool
calling, the thinking budget, and pool rotation. On a 429 (quota/rate) it
rotates to the next key; on 5xx it retries the same key with backoff. This is
how we survive the free-tier daily caps under judge load (8 keys ≈ 8x quota),
alongside the pre-cached example runs that never hit the API at all.
"""
from __future__ import annotations

import asyncio

import httpx

from config import settings

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class LLMError(RuntimeError):
    pass


class GeminiPool:
    def __init__(self, keys=None, model=None, thinking_budget=None, timeout=90.0):
        self.keys = keys or settings.gemini_key_pool()
        if not self.keys:
            raise LLMError("no Gemini keys configured (GEMINI_API_KEYS)")
        self.model = model or settings.gemini_model
        self.default_thinking = settings.gemini_thinking_budget if thinking_budget is None else thinking_budget
        self._idx = 0
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        await self.aclose()

    def _key_order(self):
        n = len(self.keys)
        return [(i, self.keys[(self._idx + i) % n]) for i in range(n)]

    async def generate(self, contents, tools=None, system=None,
                        max_output_tokens=2048, temperature=0.7, thinking_budget=None):
        """One generateContent call. Returns the raw response JSON.

        Rotates keys on 429, retries same key on 5xx. Raises LLMError if every
        key is exhausted.
        """
        tb = self.default_thinking if thinking_budget is None else thinking_budget
        body = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_output_tokens,
                "temperature": temperature,
                "thinkingConfig": {"thinkingBudget": tb},
            },
        }
        if tools:
            body["tools"] = tools
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        last_err = None
        for ki, key in self._key_order():
            url = f"{GEMINI_BASE}/models/{self.model}:generateContent?key={key}"
            for attempt in range(3):
                try:
                    r = await self._client.post(url, json=body, headers={"Content-Type": "application/json"})
                except httpx.RequestError as exc:
                    last_err = f"net:{exc}"
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                if r.status_code == 429:
                    last_err = f"429 (key #{ki})"
                    break  # quota/rate on this key -> move to the next key
                if r.status_code in (500, 502, 503):
                    last_err = f"{r.status_code}"
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                if r.status_code >= 400:
                    raise LLMError(f"{r.status_code}: {r.text[:300]}")
                self._idx = (self._idx + ki + 1) % len(self.keys)  # spread load
                return r.json()
        raise LLMError(f"all {len(self.keys)} keys exhausted: {last_err}")


# --- response parsing helpers -------------------------------------------------
def _parts(resp) -> list:
    cands = resp.get("candidates") or []
    if not cands:
        return []
    return (cands[0].get("content") or {}).get("parts") or []


def text_of(resp) -> str:
    return "".join(p.get("text", "") for p in _parts(resp) if "text" in p).strip()


def function_calls_of(resp) -> list:
    """List of {'name', 'args'} the model asked to call this turn."""
    return [p["functionCall"] for p in _parts(resp) if "functionCall" in p]


def finish_reason(resp) -> str:
    cands = resp.get("candidates") or [{}]
    return cands[0].get("finishReason", "")


def model_turn(resp) -> dict:
    """The model's content turn, to append to `contents` before replying with
    a functionResponse."""
    cands = resp.get("candidates") or [{}]
    return cands[0].get("content") or {"role": "model", "parts": []}
