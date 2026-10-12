# Overindex

**AI audience-intelligence agent for small brands & marketers.**

Type in your brand, and an LLM-powered agent autonomously investigates
[Qloo's Taste AI](https://docs.qloo.com) — fanning out across music, film, TV,
books, brands, places, podcasts and games — to reveal what your audience really
**over-indexes** on, then synthesizes a concrete marketing playbook: a cultural
persona, a surprising "Blind Spot" insight, non-obvious collaborations, content
themes and channels. You watch every real Qloo call fire in a live reasoning
trace — this is an analyst that investigates, not a search box.

> Built for the **Qloo Agentic Hackathon** (2026).

## Status

🚧 In active development.

## Quick start (Qloo client probe)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then paste your QLOO_API_KEY
QLOO_API_KEY=xxxxx python probe.py
```

## Tech stack

FastAPI · Google Gemini (ReAct agent) · Qloo Taste AI · React + TypeScript +
Tailwind · SQLite (private response cache).

## License

[MIT](./LICENSE) © 2026 Anton Bondar
