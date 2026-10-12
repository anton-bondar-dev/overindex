"""Live smoke-test for the Qloo hackathon key. Run the moment the key arrives:

    QLOO_API_KEY=xxxxx python probe.py

It makes a few real calls and dumps raw JSON so we can see the actual response
shapes (field names, where entity IDs live) before wiring up the real agent.
Nothing here is committed data — it just prints to the terminal.
"""
from __future__ import annotations

import json
import sys

from qloo_client import QlooClient, QlooError


def show(title: str, data, limit: int = 3000) -> None:
    print(f"\n===== {title} =====")
    text = json.dumps(data, indent=2, ensure_ascii=False)
    print(text[:limit] + (" ...[truncated]" if len(text) > limit else ""))


def first_entity_id(search_resp) -> str | None:
    """Best-effort pull of an entity id from a /search response (shape TBD)."""
    results = None
    if isinstance(search_resp, dict):
        for key in ("results", "data", "entities"):
            if isinstance(search_resp.get(key), list):
                results = search_resp[key]
                break
    if not results:
        return None
    top = results[0]
    if isinstance(top, dict):
        for key in ("entity_id", "id", "qloo_id", "entity_id_str"):
            if top.get(key):
                return top[key]
    return None


def main() -> None:
    try:
        qc = QlooClient()
    except QlooError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        sys.exit(1)

    with qc:
        # 1) resolve a well-known brand entity
        brand = qc.search("Blue Bottle Coffee")
        show("search 'Blue Bottle Coffee'", brand)

        # 2) resolve a movie (different entity type, to compare shapes)
        movie = qc.search("Blade Runner 2049")
        show("search 'Blade Runner 2049'", movie)

        # 3) peek at available tags
        try:
            show("tags (sample)", qc.tags())
        except QlooError as exc:
            print(f"[tags] {exc}")

        # 4) if we could grab a brand id, try a cross-domain insights call
        bid = first_entity_id(brand)
        print(f"\n[info] extracted brand entity id: {bid!r}")
        if bid:
            for ftype in ("urn:entity:artist", "urn:entity:movie", "urn:entity:place"):
                try:
                    ins = qc.insights(ftype, **{"signal.interests.entities": bid})
                    show(f"insights {ftype} <- Blue Bottle audience", ins)
                except QlooError as exc:
                    print(f"[insights {ftype}] {exc}")


if __name__ == "__main__":
    main()
