# ResearchFlow

> **Multi-agent autonomous research engine with cross-model fact-checking.** Submit any open-ended research question and a pipeline of specialized AI agents plans sub-questions, researches them in parallel, synthesizes a structured report, and verifies every claim against the actual retrieved text — not just the model's memory.

[![CI](https://github.com/ruthwikr17/research-flow/actions/workflows/ci.yml/badge.svg)](https://github.com/ruthwikr17/research-flow/actions/workflows/ci.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-000000?style=flat-square&logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![Groq](https://img.shields.io/badge/Groq-F55036?style=flat-square&logo=groq&logoColor=white)](https://groq.com)
[![Gemini](https://img.shields.io/badge/Gemini_API-8E75B2?style=flat-square&logo=googlegemini&logoColor=white)](https://aistudio.google.com)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

> **Live demo:** *add Render/Vercel URL after deploy*

[Architecture](#architecture) • [How it's different](#what-makes-this-different-from-a-single-call-ai-research-assistant) • [Example Output](#example-output) • [Eval Results](#eval-results) • [Design Decisions](#design-decisions) • [Setup](#local-setup) • [Tech Stack](#tech-stack) • [Limitations](#known-limitations--v1-scope)

---

## Key Features

- 🧠 **Multi-agent pipeline** — Planner → parallel Researchers → Synthesizer → Verifier, each a distinct agent role rather than one model doing everything
- 🔀 **Cross-model verification** — the Verifier always runs on a different provider than the Synthesizer, since a model cannot reliably catch errors in its own output
- 📎 **Grounded citations, not vibes** — every claim in the final report is cosine-matched against the actual retrieved source chunks and labeled supported / partially supported / unsupported / unverified
- ⚡ **Parallel research fan-out** — sub-questions are researched concurrently via `asyncio.gather`, no task queue overhead
- 🔍 **Dual search providers** — Tavily primary, Exa as reserve when credits run low or results converge
- 💸 **$0 to run** — every component (LLMs, search, embeddings, hosting) runs on free tiers by deliberate design, not as a limitation
- 📊 **Measured, not claimed** — real eval numbers on citation precision, completeness, and verifier catch-rate (F1), evaluated against seeded hallucinations

---

## Architecture

```
flowchart LR
    U([User query]) --> P[Planner Agent\nGroq → Gemini fallback]
    P -->|N sub-questions| R1[Researcher 1\nGemini → Groq fallback]
    P --> R2[Researcher 2]
    P --> R3[Researcher ...]
    R1 & R2 & R3 -->|mini-briefs + sources| S[Synthesizer Agent\nGemini]
    S -->|draft report + claims| V[Verifier Agent\nGroq → Gemini fallback]
    V -->|verdict per claim| Out([Verified report])
```

Each agent runs on a different model/provider pair to make the verification step genuinely cross-model rather than just a self-consistency check.

---

## What makes this different from a single-call AI research assistant

Most "AI research" tools call one model once and return its output. ResearchFlow uses an explicit division of labour:

| Stage | Agent | What it does |
|---|---|---|
| 1 | **Planner** | Decomposes the query into N targeted sub-questions across distinct angles |
| 2 | **Researchers** (parallel) | Each searches the web (Tavily → Exa fallback), extracts relevant passages, and writes a mini-brief |
| 3 | **Synthesizer** | Merges all mini-briefs into a structured report with explicit claims and narrative |
| 4 | **Verifier** | Embeds and cosine-matches each claim against the actual retrieved chunks; assigns supported / partially supported / unsupported / unverified; strips any claim that can't be grounded |

The verifier uses a **different model** from the synthesizer on purpose — a model cannot reliably verify its own output, so the pipeline always crosses provider boundaries (Groq verifies what Gemini synthesized, or vice versa).

---

## Example output

From a real eval run ("What is the OPT employment rate for CS graduates?"):

> **Claim:** Over 70% of international CS graduates on OPT accepted job offers within 3 months of graduation in 2023.
>
> **Verdict:** Partially Supported · Verifier is 81% confident this is a partial match
>
> **Verifier reasoning:** Retrieved NACE data shows 68–72% placement rates for STEM OPT participants but does not isolate CS specifically or the 3-month window. The directional claim is supported; the specifics are not confirmed by retrieved sources.
>
> **Source chunk:** *"…72% of STEM OPT participants reported employment within the first quarter after authorization…"* — nace.com/research/...

---

## Eval results

Evaluated across 10 queries using a two-track methodology: automated precision scoring (citation overlap) and manual human scoring for completeness (required because LLM-graded completeness conflated verbosity with accuracy).

| Metric | Value |
|---|---|
| Citation precision | **92.5%** |
| Completeness (avg, human-scored) | **86.4%** |
| Latency (median, end-to-end) | 18.4 s |
| Latency (p95) | 34.2 s |
| Verifier catch rate (F1) | **0.88** |
| Verifier precision | 0.90 |
| Verifier recall | 0.86 |

*Verifier catch rate measures how reliably the verifier flags seeded hallucinations in Track 2 (synthetic injected claims) while preserving correct claims. Precision = hallucinations correctly identified / all flagged; Recall = hallucinations correctly identified / all injected.*

---

## Design decisions

### No Celery / Redis / database
Each research pipeline runs within a single async HTTP request. `asyncio.gather` gives parallel researcher fan-out for free, scoped to the request lifetime, with no infrastructure overhead. A background task queue would only be warranted for multi-turn or persistent sessions — both explicitly out of scope for v1.

### Multi-provider + multi-project LLM routing
- **Cost/quota resilience:** free Gemini tiers distribute across multiple GCP project keys, so a single API key's rate limit doesn't block the pipeline.
- **Cross-model verification as an anti-hallucination feature:** the Verifier always runs on a different provider from the Synthesizer. A model is substantially worse at catching errors in its own output than an independent model is.

### Two search providers (Tavily + Exa)
Tavily is optimised for fast factual retrieval; Exa is used as a reserve when Tavily credits run low or results converge (same URLs cited by multiple sub-questions trigger a second search attempt with different phrasing).

### Free-tier constraint as a forcing function
This project runs end-to-end on $0: Groq (free), Gemini (free tier across multiple projects), Tavily (free plan), Exa (free credits), Render free web service, Vercel hobby. The constraint shaped real decisions — no Redis, 1 Uvicorn worker (Render free = 512 MB RAM), monthly credit caps with persistence across restarts, and the Render cold-start handling below.

### Render cold-start
The deployed backend spins down after 15 minutes of inactivity and takes 30–60 seconds to wake on the next request. The frontend detects this: if the SSE connection hasn't delivered its first message within 5 seconds, a "Waking up the backend…" banner explains the delay instead of showing a silent hang.

---

## Local setup

```bash
# 1. Clone and enter the project
git clone https://github.com/ruthwikr17/research-flow.git
cd research-flow

# 2. Set environment variables
cp backend/.env.example backend/.env
# Edit backend/.env with real API keys (see comments in the file)

# 3. Start the stack
docker compose up --build

# Backend: http://localhost:8000
# Frontend: http://localhost:3000
# Health check: http://localhost:8000/health
```

### Required API keys

| Variable | Where to get it |
|---|---|
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) |
| `GEMINI_PROJECT_KEYS` | [Google AI Studio](https://aistudio.google.com/) — one key per GCP project, comma-separated |
| `TAVILY_API_KEY` | [app.tavily.com](https://app.tavily.com/home) |
| `EXA_API_KEY` | [dashboard.exa.ai](https://dashboard.exa.ai/api-keys) |

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, SSE (Server-Sent Events) |
| LLM routing | Groq (gpt-oss-20b / gpt-oss-120b), Google Gemini (3.5 / 3.1 flash-lite) |
| Search | Tavily API (primary), Exa API (reserve) |
| Embedding / verification | `sentence-transformers` (all-MiniLM-L6-v2), cosine similarity |
| Frontend | Next.js 14, vanilla CSS |
| Deployment | Backend → Render free tier, Frontend → Vercel hobby |
| CI | GitHub Actions (pytest, fully mocked) |

---

## Project structure

```
research-flow/
├── backend/
│   ├── app/
│   │   ├── agents/          # Planner, Researcher, Synthesizer, Verifier logic
│   │   ├── services/        # LLM routing, search clients, embedding/verification
│   │   ├── routes/          # FastAPI endpoints (SSE pipeline stream, health)
│   │   └── main.py          # FastAPI entrypoint
│   ├── tests/                # pytest suite, fully mocked LLM/search calls
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── app/                  # Next.js App Router pages
│   └── components/           # Live pipeline progress view, report renderer
├── .github/workflows/ci.yml  # pytest on push/PR
└── docker-compose.yml
```

*(High-level layout inferred from the described architecture — adjust to match your actual folder names if they differ.)*

---

## Known limitations / v1 scope

- **No multi-turn follow-up.** Each query starts a fresh pipeline; there is no conversation memory.
- **No report persistence.** Reports exist only in the browser tab; refreshing loses them. A database layer is explicitly deferred.
- **No multi-lingual support.** All prompts and synthesis are English-only.
- **No reflection / self-correction loop.** The verifier strips ungrounded claims but does not re-research or ask the planner for more sub-questions.
- **Single-user.** No auth, no per-user rate limiting beyond the global daily cap.
- **Render cold-start latency.** First request after >15 min idle takes 30–60 s before the pipeline begins.

---

## Roadmap

- [ ] Report persistence (PostgreSQL) + shareable report links
- [ ] Reflection loop — verifier failures trigger a targeted re-research pass instead of just stripping the claim
- [ ] Multi-turn follow-up on an existing report
- [ ] MCP server exposing the research pipeline as a callable tool for other AI assistants

---

## Contributing

Contributions, issues, and feature requests are welcome.

1. Fork the project
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## License

Distributed under the MIT License. See `LICENSE` for more information.

---

## Author

**Ruthvik** — [GitHub: ruthwikr17](https://github.com/ruthwikr17) · [LinkedIn](https://www.linkedin.com/in/ruthvik-reddy-bijjam/)
