"""Defensive extractors for Qloo responses.

Qloo's response layout varies by endpoint and nests differently in places, and
the hackathon tier may differ again — so never index blindly. Every getter
tolerates missing/renamed fields and returns None rather than raising. Confirm
the real shapes with probe.py on Day 1 and adjust ONLY here.
"""
from __future__ import annotations

from typing import Any, Optional


def _first_list(resp: Any, keys: tuple) -> list:
    """Find the first list under `keys`, checking both the top level and a
    nested `results` object."""
    if not isinstance(resp, dict):
        return []
    nested = resp.get("results")
    if isinstance(nested, dict):
        for k in keys:
            if isinstance(nested.get(k), list):
                return nested[k]
    if isinstance(nested, list):
        return nested
    for k in keys:
        if isinstance(resp.get(k), list):
            return resp[k]
    return []


def search_results(resp) -> list:
    return _first_list(resp, ("entities", "results", "data"))


def insight_entities(resp) -> list:
    return _first_list(resp, ("entities", "results", "data"))


def tag_results(resp) -> list:
    return _first_list(resp, ("tags", "results", "data"))


def entity_id(e: dict) -> Optional[str]:
    for k in ("entity_id", "id", "qloo_id"):
        if e.get(k):
            return str(e[k])
    return None


def _num(*vals) -> Optional[float]:
    for v in vals:
        if isinstance(v, (int, float)):
            return float(v)
    return None


def affinity(e: dict) -> Optional[float]:
    q = e.get("query") or {}
    p = e.get("properties") or {}
    return _num(q.get("affinity"), e.get("affinity"), p.get("affinity"))


def popularity(e: dict) -> Optional[float]:
    q = e.get("query") or {}
    p = e.get("properties") or {}
    return _num(e.get("popularity"), p.get("popularity"), q.get("popularity"))


def name_of(e: dict) -> str:
    p = e.get("properties") or {}
    return e.get("name") or p.get("name") or e.get("title") or "(unknown)"


def image_of(e: dict) -> Optional[str]:
    p = e.get("properties") or {}
    img = p.get("image") or e.get("image")
    if isinstance(img, dict):
        return img.get("url")
    return img if isinstance(img, str) else None


def tag_id(t: dict) -> Optional[str]:
    for k in ("tag_id", "id", "urn"):
        if t.get(k):
            return str(t[k])
    return None
