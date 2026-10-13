# Overindex

**An AI analyst that investigates your brand's cultural audience — live — and hands you a marketing playbook grounded in [Qloo's Taste AI](https://docs.qloo.com).**

🔗 **Live demo: [overindex.overpro.fit](https://overindex.overpro.fit)** · Built for the **Qloo Agentic Hackathon** (2026)

Type in a brand. An LLM agent decides, step by step, how to interrogate Qloo —
which domains to scan, when a brand needs a proxy, when it has seen enough — and
you watch every real API call fire in a live reasoning trace. The result is a
concrete playbook: a cultural **persona**, a surprising cross-domain **Blind
Spot**, the entities your audience **over-indexes** on, and non-obvious
collaborations, content themes and channels.

This is an analyst that *investigates*, not a search box that returns rows.

<!-- SCREENSHOTS: input screen · live agent trace · results dashboard — added to docs/screenshots/ before release -->

---

## Why this is genuinely agentic

The judging bar is "multi-step autonomous tool use," not "an LLM wrapped around an
endpoint." The distinction lives in who decides the sequence of Qloo calls — and
here, the **model does**, not a script:

- **It plans and chooses tools.** Given only a brand name, the agent resolves the
  brand, then decides *which* cultural domains are worth scanning with
  `affinity_scan` and *when it has seen enough* — its reasoning streams live.
- **The path varies by brand.** Different brands lead the model to scan different
  domains, a different number of them, and to stop at different points — the
  sequence of calls is the model's, not a script's. Nothing is hard-coded.
- **It recovers.** If a small or new brand isn't in Qloo, the agent resolves 2–3
  *comparable* entities (a peer brand, a cultural anchor its buyers likely share)
  and seeds the investigation from those proxies — a real analyst's move, shown
  honestly in the trace rather than failing.
- **It decides when to stop.** The loop ends when the model judges it has enough
  signal across enough domains to describe the audience and find a non-obvious
  insight — not at a fixed call count.

The sequence of tool calls **is** the product. You see it happen in real time.

## How it works

```
brand ─▶  ReAct agent loop  (Groq gpt-oss, function-calling)
              │  plans → picks a Qloo tool → reads result → adapts → repeats
              ▼
          Qloo Taste AI          resolve_entity · affinity_scan
              │  (every call streamed to the UI as it fires)
              ▼
          grounded facts  (computed in CODE from Qloo data only)
              │  opportunity = affinity × (1 − popularity) · franchise-deduped
              │  cross-domain "blind spot" (outside the dominant lane) above a popularity floor
              ▼
          synthesis  (LLM) ──▶  persona · collaborations · content · channels
              ▼
          Audience Playbook  +  full methodology / provenance
```

A FastAPI backend drives the loop and streams every event over **Server-Sent
Events**; a React + TypeScript + Tailwind front-end renders the live
"flight-recorder" trace and the final editorial dashboard.

## Depth of Qloo use

Overindex is built *around* Qloo's signal, not bolted onto it:

- **`/search`** (typed, e.g. `types=urn:entity:brand`) to resolve a brand or its
  proxies to real Qloo entity IDs.
- **`/v2/insights`** with `signal.interests.entities` and a per-domain
  `filter.type`, fanned out across **artist, movie, tv_show, book, brand, place,
  podcast and videogame** — the agent chooses which.
- Every entity carries Qloo's **affinity** (0–1 relevance to this audience) and
  **popularity** (0–1). The interesting signal is **high affinity + low
  popularity** = ownable and non-obvious.

### Honest metrics (no fabricated lift)

Qloo exposes no population baseline, so Overindex never invents a "3× more likely
than the general population" multiplier. It shows the two raw Qloo signals
directly — **affinity** (how much this audience is into something) and
**popularity** (how mainstream it is) — and ranks opportunities by `affinity ×
(1 − popularity)`: loved **and** not-yet-obvious. The **Blind Spot** is the top
such *cross-domain* entity, outside the audience's dominant lane and above a
popularity floor (surprising **and** recognizable, not obscure noise).

### Grounded vs. proposed — kept visibly separate

Two provenance tiers never blur:

- **● Qloo data** — personas' defining tastes, affinities, the Blind Spot entity,
  opportunities: every item traces to an ID from a Qloo call *this run*.
- **◌ Agent proposal** — collaboration pitches, content angles, channel
  rationale: LLM inference, labeled as proposals. The agent may only reference
  entities actually pulled from Qloo; invented names are dropped at assembly.

No demographics are claimed anywhere (we don't pull that data), so the persona
describes cultural taste, never age/gender/income/geo.

## Real-world impact

A small brand or a solo marketer rarely has an audience-research budget. Overindex
turns a brand name into, in ~15 seconds, the kind of cultural audience brief an
agency would bill for: who these people are culturally, what they quietly love
that competitors haven't noticed, and specific collaborations, content and
channels to act on — each traceable back to Qloo's data.

## Run it locally

**Backend** (Python 3.11+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # add QLOO_API_KEY and GROQ_API_KEYS
uvicorn main:app --port 8000
```

**Front-end** (Node 18+):

```bash
cd frontend
npm install
npm run dev              # proxies /api → http://localhost:8000
```

Open the printed Vite URL. Required env: `QLOO_API_KEY` (Qloo hackathon key) and
`GROQ_API_KEYS` (one or more [console.groq.com](https://console.groq.com) keys,
comma-separated). See [`backend/.env.example`](./backend/.env.example).

### Example brands vs. your own

The four example chips **replay a frozen real investigation** (full trace +
result) from an on-disk cache, so the showcase is instant and reliable and spends
no API quota. **Typing any other brand runs the agent live** against Groq and
Qloo (~20s) — that live path is the real thing. Regenerate or extend the cache
any time with `python backend/prewarm.py "<Brand>" ...` (requires live keys; the
cache is gitignored and contains no Qloo data in this repo).

## Project layout

```
backend/
  agent_core.py    ReAct loop, tool declarations, system prompt
  synthesize.py    grounded-facts computation + LLM synthesis + assembly
  llm.py           Groq pool: key rotation + model fallback chain
  qloo/            async Qloo client, defensive parsers, mock client
  main.py          FastAPI: start run · SSE trace · fetch result
  prewarm.py       freeze example runs into the replay cache
frontend/src/
  InputScreen · RunScreen (live trace) · ResultScreen (dashboard)
  useAgentStream.ts  SSE reducer
```

## Tech stack

FastAPI · httpx (async) · Pydantic v2 · Groq (`openai/gpt-oss-120b`, OpenAI-style
function-calling) · Qloo Taste AI · React 19 + TypeScript + Vite + Tailwind v4 ·
Server-Sent Events.

## License

[MIT](./LICENSE) © 2026 Anton Bondar
