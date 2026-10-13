"""Overindex API: start an analysis, stream the live agent trace (SSE), fetch the
result.

v1 uses an in-memory run registry. The deploy phase adds the red-team ops items
(SQLite persistence so warm examples survive restarts, per-IP + global rate
limits, pre-cached example runs that bypass the live pipeline). GET /api/result
is the polling safety net if an SSE stream drops mid-run.

Run with backend/ as the working directory:
    cd backend && uvicorn main:app --port 8000
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from config import settings
from llm import make_llm
from models import AnalysisResult
from qloo import get_qloo_client
from synthesize import analyze

app = FastAPI(title="Overindex")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

_END = {"type": "_end"}


class Run:
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.result = None
        self.status = "running"   # running | done | error
        self.error: str | None = None


RUNS: dict[str, Run] = {}


# --- Pre-warmed example cache (red-team ops) --------------------------------
# An example chip replays a frozen REAL run (full trace + result) instead of
# hitting the live pipeline: instant, reliable, and it spends ZERO scarce
# free-tier quota — which is reserved for brands judges type themselves (that
# live path is what proves the agent is genuinely real-time). Built by
# prewarm.py; see backend/cache/ (gitignored — no Qloo data in the repo).
CACHE_DIR = Path(__file__).parent / "cache"

# Replay pacing: fast enough to feel snappy, slow enough that the live-trace
# animation still reads as a real investigation (it IS one, just frozen).
_REPLAY_DELAYS = {
    "run_start": 0.25, "thought": 0.3, "step_start": 0.18, "step_result": 0.42,
    "investigation_done": 0.25, "gathered": 0.2, "synthesizing": 0.8, "done": 0.1,
}


def _norm(brand: str) -> str:
    return re.sub(r"\s+", " ", (brand or "").strip().lower())


def _load_examples() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not CACHE_DIR.is_dir():
        return out
    for f in sorted(CACHE_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("brand") and data.get("events") and data.get("result"):
            out[_norm(data["brand"])] = data
    return out


EXAMPLES_CACHE: dict[str, dict] = _load_examples()

_LOG = logging.getLogger("overindex")
if not EXAMPLES_CACHE:
    _LOG.warning(
        "No example cache loaded (backend/cache is empty) — example chips will run LIVE "
        "and spend quota. Run `python prewarm.py` before serving."
    )


# --- Rate limiting: live runs only; cached replays are always free -----------
# The live path spends shared free-tier Groq + Qloo quota, and the endpoint is
# public and unauthenticated. Without this, a trivial POST loop drains the quota
# and takes the demo down. Three gates: per-IP/minute, per-day total, concurrency.
_ip_window: dict[str, deque] = defaultdict(deque)   # ip -> recent live-run timestamps
_daily = {"date": "", "count": 0}
_live_runs = 0                                      # in-flight live runs
_RL_MESSAGES = {
    "rate": "Too many analyses from your network this minute — give it a few seconds.",
    "daily": "The live demo has hit today's analysis limit. Try an example (instant), or come back tomorrow.",
    "busy": "The analyst is handling several requests right now — please retry in a few seconds.",
}


def _reserve_live_run(ip: str) -> str | None:
    """Reserve a slot for a live (quota-spending) run, or return a rejection key."""
    global _live_runs
    now = time.monotonic()
    if len(_ip_window) > 2048:  # bound the per-IP table: drop windows that emptied out
        for k in [k for k, v in _ip_window.items() if not v]:
            _ip_window.pop(k, None)
    dq = _ip_window[ip]
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= settings.per_ip_per_min:
        return "rate"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _daily["date"] != today:
        _daily.update(date=today, count=0)
    if _daily["count"] >= settings.daily_fresh_run_cap:
        return "daily"
    if _live_runs >= settings.max_live_runs:
        return "busy"
    dq.append(now)
    _daily["count"] += 1
    _live_runs += 1
    return None


async def _evict_later(run_id: str):
    """Drop a finished run after a grace window so RUNS can't grow without bound."""
    await asyncio.sleep(settings.run_grace_s)
    RUNS.pop(run_id, None)


async def _replay(run_id: str, cached: dict):
    """Stream a frozen real run back over the exact same SSE contract as a live
    run, so the frontend cannot tell the difference."""
    run = RUNS[run_id]
    try:
        run.result = AnalysisResult.model_validate(cached["result"])
    except Exception:  # noqa: BLE001 - a bad cache file must not 500 the run
        _LOG.exception("replay %s failed to load cache", run_id)
        run.status = "error"
        run.error = "replay_failed"
        await run.queue.put({"type": "error", "message": "Could not load this example — please try another.", "recoverable": True})
        await run.queue.put(_END)
        asyncio.create_task(_evict_later(run_id))
        return
    for ev in cached.get("events", []):
        await asyncio.sleep(_REPLAY_DELAYS.get(ev.get("type"), 0.28))
        await run.queue.put(ev)
    run.status = "done"
    await run.queue.put(_END)
    asyncio.create_task(_evict_later(run_id))


class AnalyzeIn(BaseModel):
    brand: str


async def _execute(run_id: str, brand: str):
    global _live_runs
    run = RUNS[run_id]

    async def emit(ev):
        await run.queue.put(ev)

    try:
        async with get_qloo_client() as qloo, make_llm() as llm:
            run.result = await asyncio.wait_for(
                analyze(brand, qloo, llm, emit=emit), timeout=settings.run_deadline_s
            )
        run.status = "done"
    except asyncio.TimeoutError:
        _LOG.warning("run %s timed out after %ss", run_id, settings.run_deadline_s)
        run.status = "error"
        run.error = "timeout"
        await run.queue.put({"type": "error", "message": "The analysis took too long and was stopped — please try again.", "recoverable": True})
    except Exception as exc:  # noqa: BLE001 - never leak internals to the client
        err_id = uuid.uuid4().hex[:8]
        _LOG.exception("run %s failed [%s]: %s", run_id, err_id, exc)
        run.status = "error"
        run.error = "failed"
        await run.queue.put({"type": "error", "message": f"The analysis hit an unexpected error ({err_id}). Please try again.", "recoverable": True})
    finally:
        _live_runs = max(0, _live_runs - 1)
        await run.queue.put(_END)
        asyncio.create_task(_evict_later(run_id))


@app.post("/api/analyze")
async def start_analyze(body: AnalyzeIn, request: Request):
    brand = (body.brand or "").strip()
    if not (2 <= len(brand) <= 200):
        raise HTTPException(422, "brand must be 2-200 characters")
    # Global registry cap (covers the cached path too): bounds memory + background
    # tasks even under a burst of example-chip clicks, which the per-IP/live limiter
    # intentionally does not gate.
    if len(RUNS) >= settings.max_total_runs:
        raise HTTPException(503, "The demo is at capacity right now — please retry in a moment.")
    run_id = uuid.uuid4().hex[:12]
    cached = EXAMPLES_CACHE.get(_norm(brand))
    if cached:
        RUNS[run_id] = Run()
        asyncio.create_task(_replay(run_id, cached))    # frozen real run — always free
        return {"run_id": run_id}
    # Live path spends shared Groq + Qloo quota — rate-limit it.
    ip = request.client.host if request.client else "unknown"
    reason = _reserve_live_run(ip)
    if reason:
        raise HTTPException(429, _RL_MESSAGES[reason])
    RUNS[run_id] = Run()
    asyncio.create_task(_execute(run_id, brand))        # live Groq + Qloo pipeline
    return {"run_id": run_id}


@app.get("/api/analyze/{run_id}/stream")
async def stream(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(404, "unknown run")

    async def gen():
        while True:
            try:
                ev = await asyncio.wait_for(run.queue.get(), timeout=8)
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"          # keep proxies from idling the stream out
                if run.status != "running":
                    break
                continue
            if ev is _END:
                break
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'end', 'status': run.status, 'result_id': run.result.id if run.result else None})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.get("/api/result/{run_id}")
async def get_result(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(404, "unknown run")
    if run.status == "running":
        return JSONResponse({"status": "running"}, status_code=202)
    if run.status == "error":
        return JSONResponse({"status": "error", "error": run.error}, status_code=500)
    return run.result.model_dump()


@app.get("/api/healthz")
async def healthz():
    # Deliberately minimal — just enough to verify a deploy (cache shipped, not
    # mock). Model name and key-pool size are withheld: they only help an abuser
    # size the quota they'd need to drain.
    return {"ok": True, "mock_qloo": settings.use_mock_qloo, "examples": sorted(EXAMPLES_CACHE)}
