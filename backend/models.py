"""The data contract shared by the agent, the API and the frontend.

Two provenance tiers are kept VISIBLY separate:
  * Qloo-grounded: EntityAffinity, DomainAffinities, BlindSpot — every item traces
    to an ID from a Qloo call this run.
  * Agent-proposed: Collaboration.pitch, ContentTheme, Channel, Persona.narrative,
    BlindSpot.line — LLM inference; the UI labels these as proposals, not facts.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

# Domains we fan out over. NOTE: "videogame", not "video_game" (verified).
DOMAINS = ["artist", "movie", "tv_show", "book", "brand", "place", "podcast", "videogame"]


# --- Qloo-grounded primitives ------------------------------------------------
class EntityAffinity(BaseModel):
    id: str
    name: str
    domain: str
    affinity: float                      # 0–1 Qloo model affinity (relevance to this audience)
    popularity: Optional[float] = None   # 0–1 general-popularity percentile


class DomainAffinities(BaseModel):
    domain: str
    entities: list[EntityAffinity] = Field(default_factory=list)


class BlindSpot(BaseModel):
    entity: EntityAffinity
    line: str      # the one-sentence wow (agent-proposed)


# --- Agent-proposed (LLM inference, clearly labeled in UI) -------------------
class Collaboration(BaseModel):
    entity: EntityAffinity       # grounded anchor
    arbitrage: float             # affinity × (1 − popularity): ownable-ness
    cross_domain: bool = False   # entity domain ≠ brand's native domain (a flag, not a score term)
    pitch: str                   # AGENT-PROPOSED


class ContentTheme(BaseModel):
    title: str
    rationale: str


class Channel(BaseModel):
    name: str
    rationale: str


class Persona(BaseModel):
    name: str
    narrative: str
    defining_tastes: list[EntityAffinity] = Field(default_factory=list)


# --- Provenance of the brand resolution (proxy-seeding is a feature) ---------
class Resolution(BaseModel):
    query: str
    resolved_id: Optional[str] = None
    resolved_name: Optional[str] = None
    method: str = "direct"        # "direct" | "proxy"
    note: Optional[str] = None    # shown as a banner when proxy-seeded


class QlooCall(BaseModel):
    endpoint: str
    params: dict = Field(default_factory=dict)
    latency_ms: Optional[int] = None


# --- Top-level result --------------------------------------------------------
class AnalysisResult(BaseModel):
    id: str
    brand: str
    created_at: str

    resolution: Optional[Resolution] = None
    persona: Optional[Persona] = None
    blind_spot: Optional[BlindSpot] = None
    domains: list[DomainAffinities] = Field(default_factory=list)
    opportunities: list[EntityAffinity] = Field(default_factory=list)  # high affinity × low popularity
    collaborations: list[Collaboration] = Field(default_factory=list)
    content_themes: list[ContentTheme] = Field(default_factory=list)
    channels: list[Channel] = Field(default_factory=list)

    qloo_calls: list[QlooCall] = Field(default_factory=list)
