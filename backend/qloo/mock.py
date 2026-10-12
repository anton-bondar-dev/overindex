"""Synthetic Qloo responses for building/testing WITHOUT the real key.

Every entity name here is OBVIOUSLY FAKE on purpose: NO real Qloo data lives in
this repo (hackathon rule + Qloo ToS). Shapes loosely mirror the documented API;
the real shapes get verified on Day 1 with probe.py and parsers.py adjusted then.

MockQlooClient is a drop-in async stand-in for QlooClient (same method surface).
"""
from __future__ import annotations

import hashlib


def _h(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()


def _fake_entities(seed: str, domain: str, n: int = 8) -> list[dict]:
    out = []
    for i in range(n):
        h = _h(seed, domain, i)
        affinity = round(max(0.95 - i * 0.07, 0.1), 3)
        popularity = round((int(h[:2], 16) % 100) / 100, 3)
        out.append(
            {
                "entity_id": f"mock:{domain}:{h[:8]}",
                "name": f"Fake {domain.title()} {h[:4].upper()}",
                "query": {"affinity": affinity},
                "properties": {"popularity": popularity, "image": None},
            }
        )
    return out


class MockQlooClient:
    def __init__(self, *_args, **_kwargs):
        self.calls: list[dict] = []

    async def aclose(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def search(self, query, **params):
        self.calls.append({"endpoint": "/search", "params": {"query": query, **params}, "latency_ms": 5})
        h = _h(query)[:8]
        return {
            "results": {
                "entities": [
                    {
                        "entity_id": f"mock:brand:{h}",
                        "name": f"{query} (mock)",
                        "properties": {"popularity": 0.6},
                    }
                ]
            }
        }

    async def tags(self, **params):
        self.calls.append({"endpoint": "/v2/tags", "params": params, "latency_ms": 5})
        return {"results": {"tags": [{"tag_id": f"urn:tag:mock:{i}", "name": f"mock-tag-{i}"} for i in range(5)]}}

    async def insights(self, filter_type, **params):
        self.calls.append({"endpoint": "/v2/insights", "params": {"filter.type": filter_type, **params}, "latency_ms": 8})
        domain = filter_type.split(":")[-1]
        seed = str(params.get("signal.interests.entities", "seed"))
        return {"results": {"entities": _fake_entities(seed, domain)}}

    async def get(self, path, **params):
        self.calls.append({"endpoint": path, "params": params, "latency_ms": 5})
        return {"results": {"entities": []}}
