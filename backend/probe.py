"""Live smoke-test for the Qloo hackathon key. Run the moment the key arrives:

    cd backend && QLOO_API_KEY=xxxxx python probe.py

Makes real calls and dumps raw JSON so we can see the actual response shapes
(field names, where IDs/affinity live) before wiring the agent. Nothing here is
committed — it just prints.
"""
from __future__ import annotations

import asyncio
import json
import sys

from qloo import parsers
from qloo.client import QlooClient, QlooError


def show(title, data, limit=3000):
    print(f"\n===== {title} =====")
    text = json.dumps(data, indent=2, ensure_ascii=False)
    print(text[:limit] + (" ...[truncated]" if len(text) > limit else ""))


async def main():
    try:
        qc = QlooClient()
    except QlooError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        sys.exit(1)

    async with qc:
        brand = await qc.search("Blue Bottle Coffee")
        show("search 'Blue Bottle Coffee'", brand)

        results = parsers.search_results(brand)
        bid = parsers.entity_id(results[0]) if results else None
        print(f"\n[info] extracted entity id: {bid!r}")

        if bid:
            for ftype in ("urn:entity:artist", "urn:entity:movie", "urn:entity:place"):
                try:
                    ins = await qc.insights(
                        ftype,
                        **{"signal.interests.entities": bid, "take": 10, "feature.explainability": "true"},
                    )
                    show(f"insights {ftype} <- Blue Bottle audience", ins)
                except QlooError as exc:
                    print(f"[insights {ftype}] {exc}")

        try:
            show("tags (filter.query='coffee')", await qc.tags(**{"filter.query": "coffee"}))
        except QlooError as exc:
            print(f"[tags] {exc}")


if __name__ == "__main__":
    asyncio.run(main())
