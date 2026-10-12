# The Lenny Growth Assistant

A grounded chat assistant over Lenny's Podcast transcripts. Every answer cites the exact episode moment, unsupported questions get a calm "not covered" instead of a guess, and conversations can become checklists, pages or Ship 30 for 30 style essays in a side viewer.

- **Grounded**: retrieval over PostgreSQL + pgvector, similarity threshold, citation chips with deep links to the YouTube timestamp.
- **Agentic**: Pi coding agent (RPC mode) runs the model with a system prompt and a real Agent Skill (`ship30-essay`).
- **Local first**: Ollama by default; optional Claude via an API key; automatic fallback to local with a visible notice.
- **Safe artifacts**: Markdown and HTML documents, sanitized and rendered in a sandboxed iframe.
- **No build step UI**: plain HTML/CSS/JS served by FastAPI.

Submission helpers: [checklist](docs/SUBMISSION-CHECKLIST.md) · [demo script](docs/demo-script.md) · [grounding review](docs/grounding-review.md)

Docs: [PRD](docs/PRD.md) · [Architecture](docs/architecture.md) · [Design](docs/design.md) · [Test plan](docs/test-plan.md) · [Build log of failures and fixes](agent-transcripts/SUMMARY.md)

## Quick start (Docker Compose)

Prerequisites: Docker Desktop, [Ollama](https://ollama.com) running on your computer, Git.

```powershell
ollama pull qwen2.5:3b
ollama pull nomic-embed-text

git clone <this repo>
cd lenny-growth-assistant
mkdir data
git clone --depth 1 https://github.com/ChatPRD/lennys-podcast-transcripts.git data/lennys-podcast-transcripts

copy .env.example .env          # then set OLLAMA_CHAT_MODEL=qwen2.5:3b (and ANTHROPIC_API_KEY if you have one)
docker compose up --build
```

Open http://localhost:8000. On first start the app imports the bundled index from `seed/index.jsonl.gz` if it exists (the author ships one, so it works in about a minute). Without it, the index is empty; build it once (about 75 minutes on a CPU laptop for a spread sample of 76 episodes, about 5 hours for all 303):

```powershell
docker compose exec app python -m app.ingest --every 4       # sample (recommended)
docker compose exec app python -m app.ingest --limit 10      # quick test
docker compose exec app python -m app.ingest                 # everything
```
Ingestion is idempotent: unchanged episodes are skipped, changed ones are re-indexed.

## Local development (without the app container)

```powershell
docker compose up -d db
npm install -g --ignore-scripts @earendil-works/pi-coding-agent    # Node 22+
cd backend
python -m venv .venv ; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\.env.example .env
python -m app.ingest --limit 10
python -m uvicorn app.main:app --port 8000
```
Terminal client: `python -m app.chat_cli "How do you hire a head of growth?"`

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DEFAULT_PROVIDER` | `ollama` | `ollama` or `anthropic` |
| `OLLAMA_CHAT_MODEL` | `qwen2.5:7b` | Any pulled model; `qwen2.5:3b` is about 5x faster on CPU |
| `ANTHROPIC_API_KEY`, `CLOUD_MODEL` | empty, `claude-haiku-5-5` | Enables the Cloud option |
| `FALLBACK_TO_LOCAL` | `true` | Retry on Ollama when the cloud call fails |
| `MIN_SIMILARITY` | `0.73` | Evidence threshold (relevant 0.74 to 0.84; off-topic at most 0.72) |
| `TOP_K`, `MAX_SOURCE_CHARS` | `4`, `900` | Smaller means a faster first word on CPU |
| `FIRST_TOKEN_TIMEOUT_S`, `IDLE_TIMEOUT_S`, `TOTAL_TIMEOUT_S` | `300`, `120`, `1500` | Request limits |
| `DATABASE_URL`, `OLLAMA_BASE_URL` | see `.env.example` | Connections |

## Project layout

```
backend/app/      API, router, retrieval, ingestion, agent client, artifacts, store
backend/pi_agent/ Pi config: SYSTEM.md, models.json (generated), skills/ship30-essay
backend/tests/    41 tests
frontend/         index.html, app.css, app.js, lib.js (+ lib.test.mjs)
docs/             PRD, architecture, design, test plan
agent-transcripts/ AI session transcripts and a summary of failures and fixes
```

## Tests

```powershell
cd backend ; python -m pytest -q          # needs the db container for API tests
node frontend/lib.test.mjs
```

## Performance (measured on a 16 GB CPU-only Windows laptop)

| Setup | First word | Total |
|---|---|---|
| qwen2.5:7b, 6 sources x 1400 chars | about 190 s | 279 s |
| qwen2.5:3b, 4 sources x 900 chars | 32 to 43 s | 46 to 61 s |
| qwen2.5:7b, 4 sources x 900 chars | 88 s | 113 s |
| Cloud (Claude) | a few seconds | a few seconds |

Essays (about 1,250 words) take several minutes on a local CPU model; use Cloud or a short request for demos.

## Known limitations

- The index covers a sample of the archive (see the "episodes indexed" note in the sidebar).
- Small local models can still garble wording or attach a citation to the wrong guest (seen with 7B: a claim about one guest cited to another source). Citation chips, quote cards and timestamps exist so readers can verify every claim.
- Model choice is a speed/quality trade-off measured on the target laptop: 3B (about 50 s, weaker grounding and attribution) vs 7B (about 2 minutes, clearly better). Cloud is the fast, high-quality option.
- No authentication or multi-user sharing in v1.
- Docker image build and the Compose path are documented and verified step by step, but run them once on a fresh machine before relying on them.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Cannot reach Ollama" | Open the Ollama app; `ollama list` should show the models. In Docker on Windows set the user variable `OLLAMA_HOST=0.0.0.0` and restart Ollama |
| `DLL load failed ... Application Control` | Not an issue with this project's dependencies (pure Python); do not install `psycopg[binary]` |
| Docker "Engine stopped" on Windows | Enable Virtual Machine Platform, run `wsl --update`, restart Windows |
| `{"detail":"Not Found"}` at `/` | The server is an old version; restart it after updating `main.py` and make sure `frontend/` exists next to `backend/` |
| Slow answers | Use `qwen2.5:3b`, lower `TOP_K`, or choose Cloud |

## Search index and evaluation

- `python -m app.seed export` writes the current index (episodes, chunks, vectors) to `seed/index.jsonl.gz`; the app imports it automatically on first start when the database is empty. The file is only valid for the embedding model it was built with.
- `python -m app.eval --write` measures retrieval (hit@k, MRR, rejection of off-topic questions) over `backend/eval/retrieval_cases.json` and writes `docs/eval-results.md`.

## Demo video

https://www.youtube.com/watch?v=SslEEG6c9p0
