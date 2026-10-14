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
BLIND_POP_CEIL = 0.55     # ...and LOW-popularity: a "blind spot" is ownable, not a mainstream hit
NATIVE_DOMAIN = "brand"   # the brand's own domain — "cross-domain" means != this
# A blind-spot hero must be a RECOGNIZABLE media entity — not a niche place (a
# specific villa/bar) or a brand. Places/brands stay in opportunities + fingerprint.
BLIND_DOMAINS = {"artist", "movie", "tv_show", "book", "podcast", "videogame"}
# A COLLABORATION must be a partnerable entity you could actually team up with —
# not a geographic place or a book.
COLLAB_DOMAINS = {"brand", "artist", "podcast", "tv_show", "videogame"}
BLIND_SPOT_MAX_NAME = 50  # the headline blind spot must read as a punchy, recognizable
                          # NAME — not a subtitle-laden 100-char book title that breaks
                          # the hero and reads as noise. Caps the candidate pool only.
OPP_POP_FLOOR = 0.12      # drop popularity artifacts / near-unknown noise from the ranking
COLLAB_POP_CAP = 0.85     # a collaboration must be a non-obvious partner, not a famous rival
# Opportunities / defining-tastes: recognizable, actionable domains (not obscure
# named venues), capped per domain so the list stays cross-domain (not 10/12 books).
OPP_DOMAINS = {"artist", "movie", "tv_show", "book", "brand", "podcast", "videogame"}
OPP_MAX_PER_DOMAIN = 3

_VOL_RE = re.compile(r"\s*[,:–-]?\s*\b(vol\.?|volume|season|part|pt\.?|chapter|episode|ep\.?|no\.?)\s*\d+.*$", re.I)


def _series_stem(name: str) -> str:
    """Collapse 'Invader Zim Vol. 3' / 'X: Season 2' / 'X: Subtitle' to a stem so one
    franchise can't flood the lists or the hero. Normalizes unicode whitespace —
    Qloo returns non-breaking / thin spaces that otherwise defeat the dedup."""
    s = re.sub(r"\s+", " ", (name or "").replace("\xa0", " ").replace(" ", " ")).strip()
    base = _VOL_RE.sub("", s)
    base = re.split(r"[:–—]", base, maxsplit=1)[0]   # drop a trailing subtitle
    base = base.strip(" :,–-")
    return base.lower() or s.lower()


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _dedupe_by_stem(entities: list) -> list:
    """Collapse franchise volumes/editions to the best (first) per stem. `entities`
    must be pre-sorted best-first."""
    best: dict[str, EntityAffinity] = {}
    for e in entities:
        best.setdefault(_series_stem(e.name), e)
    return list(best.values())


DOMAIN_LABEL = {
    "artist": "artist", "movie": "film", "tv_show": "TV show", "book": "book",
    "brand": "brand", "place": "place", "podcast": "podcast", "videogame": "video game",
}


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
    bn = _norm_name(brand)

    # Taste fingerprint: dedupe each domain's entities by franchise stem so one series
    # can't fill a lane (Invader Zim Vol. 1-4), and drop the brand itself.
    domains = [
        DomainAffinities(domain=d, entities=_dedupe_by_stem([e for e in es if _norm_name(e.name) != bn]))
        for d, es in by_domain.items()
    ]

    # Keep entities with real popularity above the floor, and NEVER the analyzed brand
    # itself (self-reference is circular; drops it from every downstream list at once).
    all_ents = [e for es in by_domain.values() for e in es]
    real = [e for e in all_ents
            if e.popularity is not None and e.popularity >= OPP_POP_FLOOR
            and _norm_name(e.name) != bn]

    # Franchise dedup across domains (best per stem), then opportunity-rank.
    best_by_stem: dict[str, EntityAffinity] = {}
    for e in sorted(real, key=_opportunity, reverse=True):
        best_by_stem.setdefault(_series_stem(e.name), e)
    deduped = sorted(best_by_stem.values(), key=_opportunity, reverse=True)

    # Opportunities / defining tastes: recognizable, actionable signals — exclude
    # obscure named venues (place) and cap any one domain so the list stays genuinely
    # cross-domain (not 10/12 books) instead of an obscurity-ranked flood.
    per_domain: Counter = Counter()
    opportunities = []
    for e in deduped:
        if e.domain not in OPP_DOMAINS or per_domain[e.domain] >= OPP_MAX_PER_DOMAIN:
            continue
        per_domain[e.domain] += 1
        opportunities.append(e)
        if len(opportunities) >= 12:
            break

    # Blind spot: a LOW-popularity recognizable MEDIA entity OUTSIDE the audience's
    # dominant lane AND not already shown as a top defining-taste — so the hero is
    # genuinely surprising, not a duplicate of opportunities[0]. No in-lane fallback:
    # if nothing surprising qualifies, the hero is suppressed.
    defining_ids = {e.id for e in opportunities[:5]}
    dom_counts = Counter(e.domain for e in opportunities if e.domain in BLIND_DOMAINS)
    dominant = dom_counts.most_common(1)[0][0] if dom_counts else None

    def _cand(e, strict=True):
        return (e.domain in BLIND_DOMAINS
                and e.id not in defining_ids
                and (not strict or e.domain != dominant)
                and e.popularity is not None
                and POP_FLOOR <= e.popularity <= BLIND_POP_CEIL
                and bool(e.name) and len(e.name) <= BLIND_SPOT_MAX_NAME)

    blind_candidates = [e for e in deduped if _cand(e, strict=True)]
    if not blind_candidates:  # nothing outside the dominant lane — allow it (still not a
        blind_candidates = [e for e in deduped if _cand(e, strict=False)]   # defining-taste, still pop-capped
    if not blind_candidates:  # last resort: widen the ceiling so there IS a hero (still a
        blind_candidates = [   # non-defining media entity; the line adapts to higher popularity)
            e for e in deduped
            if e.domain in BLIND_DOMAINS and e.id not in defining_ids and e.popularity is not None
            and POP_FLOOR <= e.popularity <= 0.80 and bool(e.name) and len(e.name) <= BLIND_SPOT_MAX_NAME
        ]

    # Collaboration candidates: a PARTNERABLE entity you could actually team up with
    # (a brand/artist/show/game/podcast — not a place or a book), ownable (pop-capped).
    collab_candidates = [
        e for e in deduped
        if e.domain in COLLAB_DOMAINS and (e.popularity is None or e.popularity <= COLLAB_POP_CAP)
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
  "persona_narrative": "2-3 sentences on the audience's cross-domain TASTE PATTERN (what kinds of culture they gravitate to, across domains). Do NOT state age/gender/income/location (no demographic data), and do NOT describe what any specific title is ABOUT — you only have names.",
  "blind_spot_name": "pick ONE name from the BLIND-SPOT candidates",
  "collaborations": ["<entity_name from the COLLABORATION candidates>", "<another>", "<another>"],
  "content_themes": [{{"title": "...", "rationale": "..."}}],
  "channels": [{{"name": "...", "rationale": "..."}}]
}}
Give UP TO 3 collaboration entity NAMES (ONLY from the collaboration candidates; fewer is fine), 3 content_themes, 3 channels. Only reference entity names that appear above.
IMPORTANT: you only know each entity's NAME + DOMAIN. Do NOT assert what any specific title/show/book is about — its plot, topic, genre or themes — you would be guessing. In content_themes and channels, write about the AUDIENCE and the marketing STRATEGY, not about what any entity contains.
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
    # Blind spot — pick from the VETTED candidate pool only. The hero LINE is TEMPLATED
    # in code from name + domain + popularity: given only names, the model fabricates
    # what entities are "about", so we assert ONLY the grounded relationship.
    blind = None
    cand_by_name = {e.name: e for e in facts["blind_candidates"]}
    bsn = proposed.get("blind_spot_name")
    entity = cand_by_name.get(bsn) if bsn else None
    if not entity and facts["blind_candidates"]:
        entity = facts["blind_candidates"][0]
    if entity:
        pop = int(round((entity.popularity or 0) * 100))
        tail = (f"and at {pop}% popularity it's still theirs to own."
                if (entity.popularity or 0) <= 0.5
                else "an unexpected cross-cultural signal to lean into early.")
        blind = BlindSpot(
            entity=entity,
            line=(f"This audience quietly over-indexes on {entity.name}, a {DOMAIN_LABEL.get(entity.domain, entity.domain)} "
                  f"most {brand} rivals would never connect to them — {tail}"),
        )

    # Collaborations — resolve ONLY from the ownable, PARTNERABLE pool; pitches are
    # TEMPLATED (name + domain + affinity + relationship), never LLM-fabricated.
    collab_pool = facts.get("collab_candidates", [])
    collab_by_name = {e.name: e for e in collab_pool}
    bn = _norm_name(brand)

    def _ok_collab(e):
        return (e and e.domain in COLLAB_DOMAINS and _norm_name(e.name) != bn
                and (e.popularity is None or e.popularity <= 0.9))

    picked, seen = [], set()
    for c in proposed.get("collaborations", []):
        nm = c if isinstance(c, str) else (c.get("entity_name") if isinstance(c, dict) else None)
        e = (collab_by_name.get(nm) or name_index.get(nm)) if nm else None
        if _ok_collab(e) and e.name not in seen:
            picked.append(e)
            seen.add(e.name)
    for e in collab_pool:   # top up (shows fewer than 3 if the partnerable pool is thin)
        if len(picked) >= 3:
            break
        if _ok_collab(e) and e.name not in seen:
            picked.append(e)
            seen.add(e.name)

    collabs = []
    for e in picked[:3]:
        pop = e.popularity if e.popularity is not None else 0.5
        collabs.append(Collaboration(
            entity=e,
            arbitrage=round(e.affinity * (1 - pop), 3),
            cross_domain=(e.domain != NATIVE_DOMAIN),
            pitch=(f"Collaborate with {e.name}, a {DOMAIN_LABEL.get(e.domain, e.domain)} this audience "
                   f"over-indexes on ({int(round(e.affinity * 100))}% affinity) but rivals overlook."),
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
