"""Gemini LLM provider with a rotating key pool.

Talks to the REST generateContent API directly for full control over tool
calling, the thinking budget, and pool rotation. On a 429 (quota/rate) it
rotates to the next key; on 5xx it retries the same key with backoff. This is
how we survive the free-tier daily caps under judge load (8 keys ≈ 8x quota),
alongside the pre-cached example runs that never hit the API at all.
"""
from __future__ import annotations

import asyncio
import json
import random

import httpx

from config import settings

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GROQ_BASE = "https://api.groq.com/openai/v1"


class LLMError(RuntimeError):
    pass


class GeminiPool:
    def __init__(self, keys=None, models=None, thinking_budget=None, timeout=30.0):
        self.keys = keys or settings.gemini_key_pool()
        if not self.keys:
            raise LLMError("no Gemini keys configured (GEMINI_API_KEYS)")
        self.models = models or settings.gemini_model_chain()
        self.model = self.models[0]  # primary, for display
        self.default_thinking = settings.gemini_thinking_budget if thinking_budget is None else thinking_budget
        # Start rotation at a random key so concurrent runs don't all stampede key[0].
        self._idx = random.randrange(len(self.keys))
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
        base = {"contents": contents}
        if tools:
            base["tools"] = tools
        if system:
            base["systemInstruction"] = {"parts": [{"text": system}]}

        last_err = None
        for model in self.models:
            gc = {"maxOutputTokens": max_output_tokens, "temperature": temperature}
            if "lite" not in model:  # lite models reject thinkingConfig
                gc["thinkingConfig"] = {"thinkingBudget": tb}
            body = {**base, "generationConfig": gc}
            for ki, key in self._key_order():
                url = f"{GEMINI_BASE}/models/{model}:generateContent"
                try:
                    r = await self._client.post(
                        url, json=body,
                        headers={"Content-Type": "application/json", "x-goog-api-key": key},
                    )
                except httpx.RequestError as exc:
                    last_err = f"net:{exc}"
                    continue  # next key
                sc = r.status_code
                if sc == 200:
                    self._idx = (self._idx + ki + 1) % len(self.keys)
                    return r.json()
                if sc == 429:
                    last_err = f"429 {model} key#{ki}"
                    continue  # quota on this key -> next key
                if sc in (500, 502, 503):
                    last_err = f"{sc} {model}"
                    break  # model overloaded -> next model
                last_err = f"{sc} {model}: {r.text[:160]}"
                break  # other error -> next model
        raise LLMError(f"all models/keys failed: {last_err}")


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


# =============================================================================
# Groq (OpenAI-compatible) — PRIMARY provider
# =============================================================================
class GroqPool:
    """OpenAI-compatible chat client for Groq with key rotation + model fallback.

    Groq is fast from any IP (Gemini is throttled from the datacenter host) and
    strong at tool-calling. Free-tier limits are per-account (tokens/day binds
    first), so the demo leans on the pre-warm cache and keeps live runs lean.
    """
    def __init__(self, keys=None, models=None, timeout=30.0):
        self.keys = keys or settings.groq_key_pool()
        if not self.keys:
            raise LLMError("no Groq keys configured (GROQ_API_KEYS)")
        self.models = models or settings.groq_model_chain()
        self.model = self.models[0]  # primary, for display
        self._idx = random.randrange(len(self.keys))
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

    async def generate(self, messages, tools=None, temperature=0.7, max_output_tokens=2048,
                       reasoning_effort="low", **_ignore):
        """One chat/completions call. Returns the raw response JSON. Rotates keys
        on 429, falls to the next model on 5xx. Extra kwargs (e.g. thinking_budget,
        system) are accepted and ignored for a drop-in signature.

        gpt-oss / qwen are REASONING models: with a low token cap their reasoning
        eats the budget before the tool_calls are emitted, so the turn comes back
        empty. reasoning_effort='low' + a roomy max_tokens keeps the loop moving."""
        body = {"messages": messages, "temperature": temperature, "max_tokens": max_output_tokens,
                "reasoning_effort": reasoning_effort}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        last_err = None
        for model in self.models:
            payload = {**body, "model": model}
            for ki, key in self._key_order():
                try:
                    r = await self._client.post(
                        f"{GROQ_BASE}/chat/completions", json=payload,
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    )
                except httpx.RequestError as exc:
                    last_err = f"net:{type(exc).__name__}"
                    continue
                sc = r.status_code
                if sc == 200:
                    self._idx = (self._idx + ki + 1) % len(self.keys)
                    return r.json()
                if sc == 429:
                    last_err = f"429 {model} key#{ki}"
                    continue
                if sc in (500, 502, 503):
                    last_err = f"{sc} {model}"
                    break  # overloaded -> next model
                last_err = f"{sc} {model}: {r.text[:160]}"
                break
        raise LLMError(f"all groq models/keys failed: {last_err}")


# --- OpenAI-format response parsing -------------------------------------------
def _oai_message(resp) -> dict:
    choices = resp.get("choices") or [{}]
    return choices[0].get("message") or {}


def oai_text(resp) -> str:
    return (_oai_message(resp).get("content") or "").strip()


def oai_reasoning(resp) -> str:
    """gpt-oss / qwen emit their chain-of-thought in a separate `reasoning` field
    (content is empty on a tool-calling turn). This is the model's real thinking,
    shown in the live trace."""
    return (_oai_message(resp).get("reasoning") or "").strip()


def oai_tool_calls(resp) -> list:
    """List of {'id', 'name', 'args'} the model asked to call this turn."""
    out = []
    for tc in (_oai_message(resp).get("tool_calls") or []):
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        out.append({"id": tc.get("id"), "name": fn.get("name"), "args": args})
    return out


def oai_assistant_msg(resp) -> dict:
    """The assistant turn (with its tool_calls) to append before the tool results.
    Preserves tool_call ids so the tool messages can reference them."""
    msg = dict(_oai_message(resp))
    msg.setdefault("role", "assistant")
    if msg.get("content") is None:
        msg["content"] = ""
    return msg


def make_llm():
    """Construct the configured primary LLM provider (Groq by default)."""
    if settings.llm_provider.lower() == "gemini":
        return GeminiPool()
    return GroqPool()
