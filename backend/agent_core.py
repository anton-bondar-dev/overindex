"""Overindex agent core: a ReAct investigation loop.

The LLM (Groq gpt-oss, OpenAI-style function calling) plans and chooses which
Qloo tools to call; we execute them and feed results back until it decides it has
enough or hits the step cap. The sequence of tool calls IS the agentic behaviour
— the model decides which domains to pursue and which to skip based on what it
sees, and a turn's calls run concurrently.

Toolset is deliberately TRIMMED: resolve_entity, affinity_scan. No demographics /
compare / trending (unverified shapes) — cut to fund genuine agency and keep the
loop cheap.
"""
from __future__ import annotations

import asyncio
import json
import time

from qloo import parsers
from llm import oai_assistant_msg, oai_reasoning, oai_text, oai_tool_calls

DOMAINS = ["artist", "movie", "tv_show", "book", "brand", "place", "podcast", "videogame"]

SYSTEM = """You are Overindex, an AI audience-intelligence analyst for small brands.
Given a brand, investigate its cultural audience with the Qloo tools and gather
enough signal to build a marketing playbook.

How to work:
1. First resolve the brand with resolve_entity. If the exact brand isn't in Qloo,
   resolve 2-3 comparable entities (a peer brand + a cultural anchor its buyers
   likely share) and use those as proxies — this is expected for small/new brands,
   not a failure. Say when you do it.
2. Then investigate: scan the cultural domains you judge most relevant with
   affinity_scan — the 4-6 most likely to reveal this audience; skip ones unlikely
   to matter. Give one short line on why for each, and adapt based on what you see.
3. Qloo gives affinity (0-1 relevance to this audience) and popularity (0-1). The
   interesting signal is HIGH affinity + relatively LOW popularity (ownable,
   non-obvious). Watch for a cross-domain "blind spot" — a surprising entity the
   brand would never guess.
4. When you have enough across several domains to describe the audience and find a
   non-obvious cross-domain insight, STOP and reply with a one-line note that
   you're done. Aim for ~6-8 scans total — be decisive, not exhaustive.

Think step by step; keep your reasoning short and concrete."""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "resolve_entity",
            "description": (
                "Look up a brand/company/product (or any cultural entity) by name in Qloo to get "
                "its entity id. Call this first. If the exact brand isn't found, resolve 2-3 "
                "comparable entities (a peer brand, or an artist/show its customers likely share)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Entity name to look up"},
                    "type": {
                        "type": "string",
                        "description": "Optional entity-type hint",
                        "enum": ["brand", "artist", "movie", "tv_show", "book", "place", "podcast", "videogame", "person"],
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "affinity_scan",
            "description": (
                "Given a resolved entity id, find the entities in a domain that this audience most "
                "over-indexes on (highest affinity). Your core investigation tool — call it for the "
                "domains you judge relevant, and adapt based on results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Qloo entity id from resolve_entity"},
                    "domain": {"type": "string", "enum": DOMAINS, "description": "Domain to scan"},
                },
                "required": ["entity_id", "domain"],
            },
        },
    },
]


async def execute_tool(qloo, name: str, args: dict):
    """Run one tool against Qloo. Returns (response_for_llm, human_summary)."""
    if name == "resolve_entity":
        # Always pass a type: an untyped search can resolve to a specific place,
        # which Qloo rejects as an interest signal. Default to brand.
        etype = args.get("type") or "brand"
        resp = await qloo.search(args["name"], types=f"urn:entity:{etype}")
        ents = parsers.search_results(resp)[:5]
        out = [{"id": parsers.entity_id(e), "name": parsers.name_of(e), "popularity": parsers.popularity(e)} for e in ents]
        summary = f"{len(out)} match(es)" + (f"; top: {out[0]['name']}" if out else " — none found")
        return {"entities": out}, summary

    if name == "affinity_scan":
        resp = await qloo.insights(
            "urn:entity:" + args["domain"],
            **{"signal.interests.entities": args["entity_id"], "take": 15},
        )
        ents = parsers.insight_entities(resp)[:15]
        out = [
            {"id": parsers.entity_id(e), "name": parsers.name_of(e),
             "affinity": parsers.affinity(e), "popularity": parsers.popularity(e)}
            for e in ents
        ]
        top = ", ".join(f"{o['name']} ({o['affinity']})" for o in out[:3])
        return {"domain": args["domain"], "entities": out}, f"{len(out)} {args['domain']}; top: {top}"

    return {"error": f"unknown tool {name}"}, f"unknown tool {name}"


def _compact_for_llm(name: str, result: dict) -> dict:
    """Trim a tool result before feeding it back to the model. affinity_scan
    returns 15 entities per domain; across 5-7 domains that blows past Groq's
    free-tier tokens-per-minute cap. The model only needs names + scores to judge
    domains and spot a blind spot — the FULL result still goes to `gathered` for
    the dashboard."""
    if name == "affinity_scan" and isinstance(result, dict) and result.get("entities"):
        return {
            "domain": result.get("domain"),
            "entities": [
                {"name": e.get("name"), "affinity": e.get("affinity")}
                for e in result["entities"][:6]
            ],
        }
    return result


async def run_investigation(brand: str, qloo, llm, emit=None, max_steps: int = 14):
    """Drive the ReAct loop. `emit` (async callable) receives RunEvent dicts for
    the live trace; everything is also collected and returned."""
    async def _emit(ev):
        if emit:
            await emit(ev)

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Investigate this brand's cultural audience: {brand}"},
    ]
    gathered, trace, steps, nudged = [], [], 0, False

    await _emit({"type": "run_start", "brand": brand})
    while steps < max_steps:
        resp = await llm.generate(messages, tools=TOOLS, temperature=0.7, max_output_tokens=2560)
        calls = oai_tool_calls(resp)
        thought = oai_text(resp) or oai_reasoning(resp)
        # Only surface a substantive reasoning line — skip bare fragments like "Done."
        substantive = bool(thought) and len(thought) >= 12 and thought.strip().rstrip(" .").lower() != "done"
        if substantive:
            await _emit({"type": "thought", "text": thought})
            trace.append({"type": "thought", "text": thought})
        if not calls:
            # gpt-oss sometimes concludes right after resolve_entity. If it hasn't
            # actually scanned anything yet, nudge it once rather than ship a
            # domain-less playbook.
            if not any(g["tool"] == "affinity_scan" for g in gathered) and not nudged:
                nudged = True
                messages.append({
                    "role": "user",
                    "content": ("You haven't scanned any domains yet. Call affinity_scan now for the "
                                "5-7 domains most relevant to this brand's audience — all in one turn."),
                })
                continue
            await _emit({"type": "investigation_done", "note": thought if substantive else ""})
            break

        messages.append(oai_assistant_msg(resp))

        # Announce every call in this turn, then run them concurrently. The model
        # usually emits one scan per turn (so they run one at a time), but if it
        # batches several into one response they execute in parallel. Each step
        # carries an id so the UI matches a result to its start even when several
        # run at once.
        batch = []
        for c in calls:
            steps += 1
            sid = f"s{steps}"
            args = c.get("args") or {}
            batch.append((sid, c["name"], args, c.get("id")))
            await _emit({"type": "step_start", "id": sid, "tool": c["name"], "args": args})

        async def _run(sid, name, args, call_id):
            t0 = time.monotonic()
            try:
                result, summary = await execute_tool(qloo, name, args)
                dt = int((time.monotonic() - t0) * 1000)
                await _emit({"type": "step_result", "id": sid, "tool": name, "summary": summary, "latency_ms": dt})
                trace.append({"type": "step", "tool": name, "args": args, "summary": summary, "latency_ms": dt})
                gathered.append({"tool": name, "args": args, "result": result})
            except Exception as exc:
                result = {"error": str(exc)}
                await _emit({"type": "step_result", "id": sid, "tool": name, "summary": f"error: {exc}", "status": "error"})
            return {"role": "tool", "tool_call_id": call_id, "content": json.dumps(_compact_for_llm(name, result))}

        tool_msgs = await asyncio.gather(*[_run(*b) for b in batch])
        messages.extend(tool_msgs)

    await _emit({"type": "gathered", "count": len(gathered)})
    return {
        "brand": brand,
        "gathered": gathered,
        "trace": trace,
        "steps": steps,
        "qloo_calls": list(getattr(qloo, "calls", [])),
    }
