"""The data contract shared by the agent, the API and the frontend.

Two provenance tiers are kept VISIBLY separate (critic #9):
  * Qloo-grounded: EntityAffinity, DomainAffinities, BlindSpot, CompareRow,
    DemographicSkew — every item traces to an ID from a Qloo call this run.
  * Agent-proposed: Collaboration.pitch, ContentTheme, Channel — LLM inference
    Qloo cannot ground; the UI labels these as proposals, not facts.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

# Domains we fan out over. NOTE: "videogame", not "video_game" (verified).
DOMAINS = ["artist", "movie", "tv_show", "book", "brand", "place", "podcast", "videogame"]


# --- Qloo-grounded primitives ------------------------------------------------
class WhySignal(BaseModel):
    """One explainability contribution (from feature.explainability)."""
    signal: str
    contribution: Optional[float] = None


class EntityAffinity(BaseModel):
    id: str
    name: str
    domain: str
    affinity: float                      # 0–1 Qloo model affinity
    popularity: Optional[float] = None   # 0–1 percentile
    lift: Optional[float] = None         # affinity / baseline affinity — REAL over-index, else None
    image: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    why: list[WhySignal] = Field(default_factory=list)


class DomainAffinities(BaseModel):
    domain: str
    entities: list[EntityAffinity] = Field(default_factory=list)


class DemographicSkew(BaseModel):
    bucket: str    # "age" | "gender" | ...
    label: str     # "25-34" | "female" | ...
    index: float   # signed skew vs baseline


class BlindSpot(BaseModel):
    entity: EntityAffinity
    line: str      # the one-sentence wow


class CompareRow(BaseModel):
    label: str
    us: float
    them: float
    delta: float


# --- Agent-proposed (LLM inference, clearly labeled in UI) -------------------
class Collaboration(BaseModel):
    entity: EntityAffinity       # grounded anchor
    arbitrage: float             # affinity × (1 − popularity_percentile)
    cross_domain: bool = False   # entity domain ≠ brand's native domain (a flag, not a score term)
    why: list[WhySignal] = Field(default_factory=list)
    pitch: str                   # AGENT-PROPOSED


class ContentTheme(BaseModel):
    title: str
    rationale: str
    angles: list[str] = Field(default_factory=list)
    grounded_in: list[str] = Field(default_factory=list)  # entity/tag ids this draws from


class Channel(BaseModel):
    name: str
    fit: Optional[float] = None
    rationale: str


class Persona(BaseModel):
    name: str
    narrative: str
    demographic_skew: list[DemographicSkew] = Field(default_factory=list)
    defining_tastes: list[EntityAffinity] = Field(default_factory=list)


# --- Provenance of the brand resolution (critic #3: proxy-seeding is a feature)
class Resolution(BaseModel):
    query: str
    resolved_id: Optional[str] = None
    resolved_name: Optional[str] = None
    method: str = "direct"        # "direct" | "proxy"
    proxies: list[EntityAffinity] = Field(default_factory=list)
    note: Optional[str] = None    # shown in the trace when proxy-seeded


class QlooCall(BaseModel):
    endpoint: str
    params: dict = Field(default_factory=dict)
    count: Optional[int] = None
    latency_ms: Optional[int] = None
    cached: bool = False


# --- Top-level result --------------------------------------------------------
class AnalysisResult(BaseModel):
    id: str
    brand: str
    competitor: Optional[str] = None
    region: Optional[str] = None
    category: Optional[str] = None
    created_at: str

    resolution: Optional[Resolution] = None
    persona: Optional[Persona] = None
    blind_spot: Optional[BlindSpot] = None
    domains: list[DomainAffinities] = Field(default_factory=list)
    opportunities: list[EntityAffinity] = Field(default_factory=list)  # high affinity × low popularity
    competitor_compare: list[CompareRow] = Field(default_factory=list)
    collaborations: list[Collaboration] = Field(default_factory=list)
    content_themes: list[ContentTheme] = Field(default_factory=list)
    channels: list[Channel] = Field(default_factory=list)

    qloo_calls: list[QlooCall] = Field(default_factory=list)


# --- Streamed run events (SSE contract) --------------------------------------
class RunEvent(BaseModel):
    """Permissive envelope streamed over SSE. `type` drives the frontend reducer:
    plan | step_start | thought | step_result | section_ready | stats | done | error
    """
    type: str
    id: Optional[str] = None
    kind: Optional[str] = None            # resolve|tags|affinity|baseline|demographics|compare|trend|synthesize
    title: Optional[str] = None
    text: Optional[str] = None
    call: Optional[dict] = None           # {method, endpoint, params}
    status: Optional[str] = None          # ok | error
    summary: Optional[str] = None
    latency_ms: Optional[int] = None
    stats: Optional[dict] = None
    section: Optional[str] = None
    data: Optional[dict] = None
    steps: Optional[list] = None
    message: Optional[str] = None
    recoverable: Optional[bool] = None
    result_id: Optional[str] = None
