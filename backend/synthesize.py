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
import uuid
from datetime import datetime, timezone

from models import (
    AnalysisResult, BlindSpot, Channel, Collaboration, ContentTheme,
    DomainAffinities, EntityAffinity, Persona, QlooCall,
)
from llm import text_of
from agent_core import run_investigation

POP_FLOOR = 0.15          # blind-spot candidates must be at least this recognizable
NATIVE_DOMAIN = "brand"   # the brand's own domain — "cross-domain" means != this
BLIND_SPOT_MAX_NAME = 50  # the headline blind spot must read as a punchy, recognizable
                          # NAME — not a subtitle-laden 100-char book title that breaks
                          # the hero and reads as noise. Caps the candidate pool only.


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


def build_facts(gathered) -> dict:
    by_domain = _entities_by_domain(gathered)
    # Honest relative index: how far above this audience's AVERAGE (within a domain)
    # an entity sits. Labeled "x the audience's average" in the UI — NOT a population
    # lift (Qloo exposes no population baseline), and never fabricated.
    for es in by_domain.values():
        affs = [e.affinity for e in es if e.affinity]
        mean = sum(affs) / len(affs) if affs else 0.0
        for e in es:
            e.lift = round(e.affinity / mean, 2) if mean else None
    domains = [DomainAffinities(domain=d, entities=es) for d, es in by_domain.items()]
    all_ents = [e for es in by_domain.values() for e in es]
    opportunities = sorted(all_ents, key=_opportunity, reverse=True)
    blind_candidates = [
        e for e in opportunities
        if e.domain != NATIVE_DOMAIN
        and (e.popularity is None or e.popularity >= POP_FLOOR)
        and e.name and len(e.name) <= BLIND_SPOT_MAX_NAME
    ]
    return {
        "by_domain": by_domain,
        "domains": domains,
        "opportunities": opportunities[:12],
        "blind_candidates": blind_candidates[:5],
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

    prompt = f"""Brand: {brand}

Audience affinities by domain (from Qloo; affinity 0-1 = relevance to this audience, popularity 0-1):
{chr(10).join(dom_lines)}

Blind-spot candidates (cross-domain, surprising but recognizable):
{chr(10).join(cand_lines)}

Write a marketing playbook as JSON with EXACTLY these keys:
{{
  "persona_name": "short evocative name for the audience",
  "persona_narrative": "2-3 sentences. Describe their cultural taste. Do NOT state age, gender, income or location — we have no demographic data.",
  "blind_spot_name": "pick ONE name from the blind-spot candidates",
  "blind_spot_line": "one memorable sentence about that surprising affinity",
  "collaborations": [{{"entity_name": "<name from the lists above>", "pitch": "one concrete line"}}],
  "content_themes": [{{"title": "...", "rationale": "..."}}],
  "channels": [{{"name": "...", "rationale": "..."}}]
}}
Give 3 collaborations, 3 content_themes, 3 channels. Only reference entity names that appear above.
Return ONLY the JSON."""

    resp = await llm.generate(
        [{"role": "user", "parts": [{"text": prompt}]}],
        max_output_tokens=2048, temperature=0.85, thinking_budget=256,
    )
    return _parse_json(text_of(resp))


def assemble(brand: str, facts: dict, proposed: dict, qloo_calls=None, resolution=None) -> AnalysisResult:
    name_index = {e.name: e for es in facts["by_domain"].values() for e in es}

    # blind spot — entity must be one we actually pulled
    blind = None
    bsn = proposed.get("blind_spot_name")
    entity = name_index.get(bsn) if bsn else None
    if not entity and facts["blind_candidates"]:
        entity = facts["blind_candidates"][0]
    if entity:
        line = proposed.get("blind_spot_line") or f"This audience quietly over-indexes on {entity.name}."
        blind = BlindSpot(entity=entity, line=line)

    # collaborations — drop any the LLM invented (grounding enforcement)
    collabs = []
    for c in proposed.get("collaborations", []):
        e = name_index.get(c.get("entity_name"))
        if not e:
            continue
        pop = e.popularity if e.popularity is not None else 0.5
        collabs.append(Collaboration(
            entity=e,
            arbitrage=round(e.affinity * (1 - pop), 3),
            cross_domain=(e.domain != NATIVE_DOMAIN),
            pitch=c.get("pitch", ""),
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


async def analyze(brand: str, qloo, llm, emit=None, max_steps: int = 14) -> AnalysisResult:
    """Full pipeline: investigate (ReAct) -> build grounded facts -> LLM synthesis
    -> assembled AnalysisResult."""
    inv = await run_investigation(brand, qloo, llm, emit=emit, max_steps=max_steps)
    if emit:
        await emit({"type": "synthesizing"})
    facts = build_facts(inv["gathered"])
    proposed = await synthesize(brand, facts, llm)
    qcalls = [QlooCall(endpoint=c.get("endpoint", ""), params=c.get("params", {}),
                       latency_ms=c.get("latency_ms")) for c in inv["qloo_calls"]]
    result = assemble(brand, facts, proposed, qloo_calls=qcalls)
    if emit:
        await emit({"type": "done", "result_id": result.id})
    return result
