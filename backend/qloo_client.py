"""Minimal client for the Qloo Hackathon API.

Base URL: https://hackathon.api.qloo.com
Auth:     header  X-Api-Key: <key>   (NOT Bearer, NOT a query param)
Docs:     https://docs.qloo.com

Call /search and /v2/tags first to resolve valid Qloo IDs, then pass those
IDs into /v2/insights. Invalid params are silently ignored by the API, so
always sanity-check responses while developing.
"""
from __future__ import annotations

import os

import httpx

QLOO_BASE_URL = os.getenv("QLOO_BASE_URL", "https://hackathon.api.qloo.com")


class QlooError(RuntimeError):
    """Raised on a missing key or a non-2xx response."""


class QlooClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = QLOO_BASE_URL,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("QLOO_API_KEY")
        if not self.api_key:
            raise QlooError("QLOO_API_KEY is not set (export it or pass api_key=...)")
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
            timeout=timeout,
        )

    # -- lifecycle -----------------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "QlooClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # -- core ----------------------------------------------------------------
    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self._client.get(path, params=params or {})
        if resp.status_code >= 400:
            raise QlooError(f"GET {path} -> {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    # -- lookup / validation (resolve IDs first) -----------------------------
    def search(self, query: str, **params) -> dict:
        """Entity lookup by name -> Qloo IDs.  GET /search"""
        return self._get("/search", {"query": query, **params})

    def tags(self, **params) -> dict:
        """Valid tag IDs for interests / cuisines / genres.  GET /v2/tags"""
        return self._get("/v2/tags", params)

    # -- main insights endpoint ---------------------------------------------
    def insights(self, filter_type: str, **params) -> dict:
        """Cross-domain insights & recommendations.  GET /v2/insights

        filter_type is a urn:entity:* value (brand, movie, artist, place, ...).
        Pass dotted params via dict-unpacking, e.g.:
            insights("urn:entity:brand", **{"signal.interests.entities": entity_id})
        """
        return self._get("/v2/insights", {"filter.type": filter_type, **params})

    # -- escape hatch for endpoints we wire up after the API deep-dive -------
    def get(self, path: str, **params) -> dict:
        """Raw GET against any path (audiences / compare / trending / ...)."""
        return self._get(path, params)
