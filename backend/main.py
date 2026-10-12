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
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from config import settings
from llm import GeminiPool
from qloo import get_qloo_client
from synthesize import analyze

app = FastAPI(title="Overindex")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

_END = {"type": "_end"}


class Run:
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.result = None
        self.status = "running"   # running | done | error
        self.error: str | None = None


RUNS: dict[str, Run] = {}


class AnalyzeIn(BaseModel):
    brand: str


async def _execute(run_id: str, brand: str):
    run = RUNS[run_id]

    async def emit(ev):
        await run.queue.put(ev)

    try:
        async with get_qloo_client() as qloo, GeminiPool() as llm:
            run.result = await analyze(brand, qloo, llm, emit=emit)
        run.status = "done"
    except Exception as exc:  # noqa: BLE001 - surface any failure to the stream
        run.status = "error"
        run.error = str(exc)
        await run.queue.put({"type": "error", "message": str(exc), "recoverable": False})
    finally:
        await run.queue.put(_END)


@app.post("/api/analyze")
async def start_analyze(body: AnalyzeIn):
    brand = (body.brand or "").strip()
    if not (2 <= len(brand) <= 200):
        raise HTTPException(422, "brand must be 2-200 characters")
    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = Run()
    asyncio.create_task(_execute(run_id, brand))
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
    return {
        "ok": True,
        "model": settings.gemini_model,
        "gemini_keys": len(settings.gemini_key_pool()),
        "mock_qloo": settings.use_mock_qloo,
    }
