"""Turn gathered Qloo signal into an AnalysisResult playbook, then orchestrate
the whole analyze() pipeline (investigate -> synthesize).

Grounding discipline (red-team):
- The GROUNDED layer (domains, opportunities, the blind-spot ENTITY) is computed
  in CODE from Qloo facts only: affinity + popularity, never a fabricated lift.
- The PROPOSED layer (persona narrative, collab pitches, content, channels) is
  LLM inference, kept separate and only allowed to reference entities we actually
  pulled.
- "Opportunity" = affinity * (1 - popularity): high relevance + low popularity =
  ownable. Blind spot = the top such CROSS-DOMAIN entity passing a popularity
  FLOOR (surprising AND recognizable, not obscure noise).
- No demographics anywhere (we don't pull that data), so the persona must not
  assert age/gender/geo.
"""
from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from datetime import datetime, timezone

from models import (
    AnalysisResult, BlindSpot, Channel, Collaboration, ContentTheme,
    DomainAffinities, EntityAffinity, Persona, QlooCall, Resolution,
)
from llm import oai_text
from agent_core import run_investigation

POP_FLOOR = 0.15          # blind-spot candidates must be at least this recognizable
NATIVE_DOMAIN = "brand"   # the brand's own domain — "cross-domain" means != this
BLIND_SPOT_MAX_NAME = 50  # the headline blind spot must read as a punchy, recognizable
                          # NAME — not a subtitle-laden 100-char book title that breaks
                          # the hero and reads as noise. Caps the candidate pool only.
OPP_POP_FLOOR = 0.05      # drop popularity=0 data artifacts from "ownable" ranking
COLLAB_POP_CAP = 0.85     # a collaboration must be a non-obvious partner, not a famous rival

_VOL_RE = re.compile(r"\s*[,:–-]?\s*\b(vol\.?|volume|season|part|pt\.?|chapter|episode|ep\.?|no\.?)\s*\d+.*$", re.I)


def _series_stem(name: str) -> str:
    """Collapse 'Invader Zim Vol. 3' / 'X: Season 2' to a stem so one franchise
    (and its volume artifacts) can't flood the lists or the hero."""
    base = _VOL_RE.sub("", name or "").strip(" :,–-")
    return base.lower() or (name or "").lower()


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _entities_by_domain(gathered) -> dict:
    by_domain: dict[str, list[EntityAffinity]] = {}
    for g in gathered:
        if g["tool"] != "affinity_scan":
            continue
        dom = g["result"].get("domain")
        for e in g["result"].get("entities", []):
            aff = e.get("affinity")
            if aff is None:
                continue
            pop = e.get("popularity")
            ea = EntityAffinity(
                id=e.get("id") or "",
                name=e.get("name") or "?",
                domain=dom,
                affinity=float(aff),
                popularity=(float(pop) if pop is not None else None),
            )
            by_domain.setdefault(dom, []).append(ea)
    for dom in by_domain:
        by_domain[dom].sort(key=lambda x: x.affinity, reverse=True)
    return by_domain


def _opportunity(ea: EntityAffinity) -> float:
    pop = ea.popularity if ea.popularity is not None else 0.5
    return ea.affinity * (1 - pop)


def build_facts(gathered, brand: str = "") -> dict:
    by_domain = _entities_by_domain(gathered)
    domains = [DomainAffinities(domain=d, entities=es) for d, es in by_domain.items()]
    all_ents = [e for es in by_domain.values() for e in es]

    # Drop popularity artifacts (0.0 / missing): opportunity = affinity*(1-pop) would
    # otherwise rank a pop=0 data gap as the #1 "ownable" signal.
    real = [e for e in all_ents if e.popularity is not None and e.popularity >= OPP_POP_FLOOR]

    # Franchise/volume normalization: keep the best-scoring entity per (domain, stem)
    # so one series (and its "Vol. N" artifacts) can't flood the lists or the hero.
    best_by_stem: dict[tuple, EntityAffinity] = {}
    for e in sorted(real, key=_opportunity, reverse=True):
        best_by_stem.setdefault((e.domain, _series_stem(e.name)), e)
    deduped = sorted(best_by_stem.values(), key=_opportunity, reverse=True)
    opportunities = deduped[:12]

    # Blind-spot candidates: cross-domain, recognizable (pop floor), punchy name, AND
    # outside the audience's DOMINANT media domain — so the blind spot is a genuinely
    # different lane, not the brand's own category in another format (Nike -> basketball).
    dom_counts = Counter(e.domain for e in deduped[:8])
    dominant = dom_counts.most_common(1)[0][0] if dom_counts else None

    def _cand(e, allow_dominant):
        return (e.domain != NATIVE_DOMAIN
                and (allow_dominant or e.domain != dominant)
                and (e.popularity is None or e.popularity >= POP_FLOOR)
                and e.name and len(e.name) <= BLIND_SPOT_MAX_NAME)

    blind_candidates = [e for e in deduped if _cand(e, allow_dominant=False)]
    if not blind_candidates:  # nothing outside the dominant lane — relax
        blind_candidates = [e for e in deduped if _cand(e, allow_dominant=True)]

    # Collaboration candidates: ownable (pop-capped) and never the brand itself — a
    # collab should be a non-obvious partner, not "team up with your biggest rival".
    bn = _norm_name(brand)
    collab_candidates = [
        e for e in deduped
        if (e.popularity is None or e.popularity <= COLLAB_POP_CAP) and _norm_name(e.name) != bn
    ][:10]

    return {
        "by_domain": by_domain,
        "domains": domains,
        "opportunities": opportunities,
        "blind_candidates": blind_candidates[:5],
        "collab_candidates": collab_candidates,
    }


def _parse_json(txt: str) -> dict:
    txt = (txt or "").strip()
    if "```" in txt:
        # pull the fenced block
        parts = txt.split("```")
        if len(parts) >= 2:
            txt = parts[1]
            if txt.lstrip().lower().startswith("json"):
                txt = txt.lstrip()[4:]
    s, e = txt.find("{"), txt.rfind("}")
    if s < 0 or e <= s:
        return {}
    try:
        return json.loads(txt[s:e + 1])
    except json.JSONDecodeError:
        return {}


async def synthesize(brand: str, facts: dict, llm) -> dict:
    dom_lines = []
    for d in facts["domains"]:
        top = "; ".join(
            f"{e.name} (aff {e.affinity:.2f}, pop {e.popularity if e.popularity is not None else '?'})"
            for e in d.entities[:6]
        )
        dom_lines.append(f"- {d.domain}: {top}")
    cand_lines = [
        f"- {e.name} [{e.domain}] aff {e.affinity:.2f} pop {e.popularity}"
        for e in facts["blind_candidates"]
    ] or ["- (none)"]
    collab_lines = [
        f"- {e.name} [{e.domain}] aff {e.affinity:.2f} pop {e.popularity}"
        for e in facts["collab_candidates"]
    ] or ["- (none)"]

    prompt = f"""Brand: {brand}

Audience affinities by domain (from Qloo; affinity 0-1 = relevance to this audience, popularity 0-1):
{chr(10).join(dom_lines)}

Blind-spot candidates (cross-domain, surprising but recognizable):
{chr(10).join(cand_lines)}

Collaboration candidates (ownable — high affinity, lower fame; pick collaborations ONLY from these):
{chr(10).join(collab_lines)}

Write a marketing playbook as JSON with EXACTLY these keys:
{{
  "persona_name": "short evocative name for the audience",
  "persona_narrative": "2-3 sentences. Describe their cultural taste. Do NOT state age, gender, income or location — we have no demographic data.",
  "blind_spot_name": "pick ONE name from the BLIND-SPOT candidates",
  "blind_spot_line": "one memorable sentence about that surprising affinity",
  "collaborations": [{{"entity_name": "<name from the COLLABORATION candidates>", "pitch": "one concrete line"}}],
  "content_themes": [{{"title": "...", "rationale": "..."}}],
  "channels": [{{"name": "...", "rationale": "..."}}]
}}
Give 3 collaborations (ONLY from the collaboration candidates — never the brand itself or a famous rival), 3 content_themes, 3 channels. Only reference entity names that appear above.
Return ONLY the JSON."""

    resp = await llm.generate(
        [{"role": "user", "content": prompt}],
        max_output_tokens=3072, temperature=0.85,
    )
    return _parse_json(oai_text(resp))


def assemble(brand: str, facts: dict, proposed: dict, qloo_calls=None, resolution=None) -> AnalysisResult:
    name_index = {e.name: e for es in facts["by_domain"].values() for e in es}

    # blind spot — the LLM may only pick from the VETTED candidate pool (cross-domain,
    # above the popularity floor, punchy name). Resolving against ALL pulled entities
    # would let a native-brand, over-popular, or 100-char title through as the hero.
    blind = None
    cand_by_name = {e.name: e for e in facts["blind_candidates"]}
    bsn = proposed.get("blind_spot_name")
    entity = cand_by_name.get(bsn) if bsn else None
    if not entity and facts["blind_candidates"]:
        entity = facts["blind_candidates"][0]
    if entity:
        line = proposed.get("blind_spot_line") or f"This audience quietly over-indexes on {entity.name}."
        blind = BlindSpot(entity=entity, line=line)

    # collaborations — resolve ONLY from the ownable collab pool, and hard-exclude the
    # brand itself or a famous incumbent even if the model picked one (grounding + the
    # "ownable" thesis). Top up from the pool if the model under-delivered.
    collab_pool = facts.get("collab_candidates", [])
    collab_by_name = {e.name: e for e in collab_pool}
    bn = _norm_name(brand)

    def _ok_collab(e):
        return e and _norm_name(e.name) != bn and (e.popularity is None or e.popularity <= 0.9)

    picked, seen = [], set()
    for c in proposed.get("collaborations", []):
        e = collab_by_name.get(c.get("entity_name")) or name_index.get(c.get("entity_name"))
        if _ok_collab(e) and e.name not in seen:
            picked.append((e, c.get("pitch", "")))
            seen.add(e.name)
    for e in collab_pool:  # ensure 3 ownable collabs even if the model gave too few
        if len(picked) >= 3:
            break
        if _ok_collab(e) and e.name not in seen:
            picked.append((e, ""))
            seen.add(e.name)

    collabs = []
    for e, pitch in picked[:3]:
        pop = e.popularity if e.popularity is not None else 0.5
        collabs.append(Collaboration(
            entity=e,
            arbitrage=round(e.affinity * (1 - pop), 3),
            cross_domain=(e.domain != NATIVE_DOMAIN),
            pitch=pitch,
        ))

    persona = Persona(
        name=proposed.get("persona_name", "Your audience"),
        narrative=proposed.get("persona_narrative", ""),
        defining_tastes=facts["opportunities"][:5],
    )
    content = [ContentTheme(title=t.get("title", ""), rationale=t.get("rationale", ""))
               for t in proposed.get("content_themes", [])]
    channels = [Channel(name=ch.get("name", ""), rationale=ch.get("rationale", ""))
                for ch in proposed.get("channels", [])]

    return AnalysisResult(
        id=uuid.uuid4().hex[:12],
        brand=brand,
        created_at=datetime.now(timezone.utc).isoformat(),
        resolution=resolution,
        persona=persona,
        blind_spot=blind,
        domains=facts["domains"],
        opportunities=facts["opportunities"][:12],
        collaborations=collabs,
        content_themes=content,
        channels=channels,
        qloo_calls=qloo_calls or [],
    )


def _build_resolution(brand: str, gathered) -> "Resolution | None":
    """Was the brand found in Qloo directly, or did the agent seed from comparable
    entities (proxy)? Surfaced honestly on the result when it's a proxy."""
    resolved, scan_ids = [], set()
    for g in gathered:
        if g["tool"] == "resolve_entity":
            resolved.extend(g["result"].get("entities", []))
        elif g["tool"] == "affinity_scan":
            sid = (g.get("args") or {}).get("entity_id")
            if sid:
                scan_ids.add(sid)
    if not resolved:
        return None
    used = next((e for e in resolved if e.get("id") in scan_ids), resolved[0])
    used_name = used.get("name") or brand
    bn, un = _norm_name(brand), _norm_name(used_name)
    direct = bn == un or (bool(bn) and (bn in un or un in bn))
    if direct:
        return Resolution(query=brand, resolved_id=used.get("id"), resolved_name=used_name, method="direct")
    proxies = [e.get("name") for e in resolved if e.get("id") in scan_ids and e.get("name")][:3] or [used_name]
    return Resolution(
        query=brand, resolved_id=used.get("id"), resolved_name=used_name, method="proxy",
        note=f"“{brand}” isn't in Qloo — analyzed via comparable entities its audience shares: "
             + ", ".join(proxies) + ".",
    )


async def analyze(brand: str, qloo, llm, emit=None, max_steps: int = 14) -> AnalysisResult:
    """Full pipeline: investigate (ReAct) -> build grounded facts -> LLM synthesis
    -> assembled AnalysisResult."""
    inv = await run_investigation(brand, qloo, llm, emit=emit, max_steps=max_steps)
    if emit:
        await emit({"type": "synthesizing"})
    facts = build_facts(inv["gathered"], brand)
    proposed = await synthesize(brand, facts, llm)
    qcalls = [QlooCall(endpoint=c.get("endpoint", ""), params=c.get("params", {}),
                       latency_ms=c.get("latency_ms")) for c in inv["qloo_calls"]]
    resolution = _build_resolution(brand, inv["gathered"])
    result = assemble(brand, facts, proposed, qloo_calls=qcalls, resolution=resolution)
    if emit:
        await emit({"type": "done", "result_id": result.id})
    return result
