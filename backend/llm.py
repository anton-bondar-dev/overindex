"""Groq LLM provider (OpenAI-compatible) with a rotating key pool.

Talks to Groq's chat/completions API. Groq is fast from any IP (Google's Gemini
endpoint heavily throttles the datacenter host) and strong at tool-calling. On a
429 it rotates to the next key; on 5xx it falls to the next model. The pre-warm
cache serves common brands without hitting the API at all.
"""
from __future__ import annotations

import json
import random

import httpx

from config import settings

GROQ_BASE = "https://api.groq.com/openai/v1"


class LLMError(RuntimeError):
    pass


class GroqPool:
    """OpenAI-compatible chat client for Groq with key rotation + model fallback.

    Free-tier limits are per-account (tokens/minute binds first), so the demo
    leans on the pre-warm cache and keeps live runs lean.
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
        on 429, falls to the next model on 5xx.

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
    """gpt-oss / qwen emit their chain-of-thought in a separate reasoning field
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
    """Construct the LLM provider (Groq)."""
    return GroqPool()
