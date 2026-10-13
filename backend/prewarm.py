"""Pre-warm the example cache: run the REAL pipeline for each showcase brand and
freeze the full trace + result to backend/cache/{slug}.json.

Why: judges clicking an example chip then get an instant, quota-free REPLAY of a
real run (same live trace, same dashboard). The live Gemini/Qloo pipeline is
reserved for brands they type themselves — which is what proves the agent is
genuinely real-time. Re-run this after any pipeline change.

    cd backend && USE_MOCK_QLOO=0 python prewarm.py
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from config import settings
from llm import GeminiPool
from qloo import get_qloo_client
from synthesize import analyze

CACHE_DIR = Path(__file__).parent / "cache"

# Keep in lock-step with EXAMPLES in frontend/src/InputScreen.tsx.
EXAMPLES = ["Patagonia", "A24", "Blue Bottle Coffee", "Liquid Death"]


def _slug(brand: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-")


async def warm_one(brand: str) -> None:
    events: list[dict] = []

    async def emit(ev):
        events.append(ev)

    async with get_qloo_client() as qloo, GeminiPool() as llm:
        result = await analyze(brand, qloo, llm, emit=emit)

    payload = {"brand": brand, "events": events, "result": result.model_dump()}
    CACHE_DIR.mkdir(exist_ok=True)
    out = CACHE_DIR / f"{_slug(brand)}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Quality gate: print the headline facts so a weak example is obvious.
    persona = result.persona.name if result.persona else "—"
    blind = f"{result.blind_spot.entity.name} [{result.blind_spot.entity.domain}]" if result.blind_spot else "—"
    print(
        f"OK {brand}: persona={persona!r} blind_spot={blind} "
        f"domains={len(result.domains)} collabs={len(result.collaborations)} "
        f"opps={len(result.opportunities)} qloo_calls={len(result.qloo_calls)} "
        f"events={len(events)} -> {out.name}"
    )


async def main() -> None:
    if settings.use_mock_qloo:
        print("REFUSING: USE_MOCK_QLOO=1 — cache would be synthetic. Set USE_MOCK_QLOO=0.")
        return
    print(f"Pre-warming {len(EXAMPLES)} examples into {CACHE_DIR} ...")
    for brand in EXAMPLES:
        try:
            await warm_one(brand)
        except Exception as exc:  # noqa: BLE001 - report and continue to the next
            print(f"FAIL {brand}: {exc!r}")


if __name__ == "__main__":
    asyncio.run(main())
