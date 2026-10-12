"""Async client for the Qloo Hackathon API.

Base URL: https://hackathon.api.qloo.com   Auth: header  X-Api-Key
Resolve IDs via /search and /v2/tags first, then feed them to /v2/insights.
Invalid params are silently ignored by the API, so verify shapes live on Day 1.
"""
from __future__ import annotations

import asyncio
import time

import httpx

from config import settings


class QlooError(RuntimeError):
    """Missing key or non-2xx response."""


class QlooClient:
    def __init__(self, api_key=None, base_url=None, concurrency=None, timeout=30.0):
        self.api_key = api_key or settings.qloo_api_key
        if not self.api_key:
            raise QlooError("QLOO_API_KEY is not set (export it or pass api_key=...)")
        self.base_url = (base_url or settings.qloo_base_url).rstrip("/")
        self._sem = asyncio.Semaphore(concurrency or settings.max_qloo_concurrency)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
            timeout=timeout,
        )
        self.calls: list[dict] = []  # endpoint/params/latency log for the methodology table

    async def aclose(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        await self.aclose()

    async def _get(self, path, params=None, retries=3):
        params = params or {}
        async with self._sem:
            for attempt in range(retries + 1):
                t0 = time.monotonic()
                try:
                    resp = await self._client.get(path, params=params)
                except httpx.RequestError as exc:
                    if attempt < retries:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    raise QlooError(f"GET {path} network error: {exc}") from exc
                latency_ms = int((time.monotonic() - t0) * 1000)
                if resp.status_code == 429 and attempt < retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                if resp.status_code >= 400:
                    raise QlooError(f"GET {path} -> {resp.status_code}: {resp.text[:300]}")
                self.calls.append({"endpoint": path, "params": dict(params), "latency_ms": latency_ms})
                return resp.json()
            raise QlooError(f"GET {path} -> 429 after {retries} retries")

    async def search(self, query, **params):
        """Entity lookup by name -> Qloo IDs.  GET /search"""
        return await self._get("/search", {"query": query, **params})

    async def tags(self, **params):
        """Valid tag IDs for interests / cuisines / genres.  GET /v2/tags"""
        return await self._get("/v2/tags", params)

    async def insights(self, filter_type, **params):
        """Cross-domain insights & recommendations.  GET /v2/insights

        e.g. insights("urn:entity:artist", **{"signal.interests.entities": brand_id})
        """
        return await self._get("/v2/insights", {"filter.type": filter_type, **params})

    async def get(self, path, **params):
        """Raw GET escape hatch for endpoints wired up after the Day-1 verify."""
        return await self._get(path, params)
