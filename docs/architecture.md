# Architecture

## 1. Overview

```
Browser (plain ES modules, served by FastAPI)
   |  POST /api/sessions/{id}/messages   <- Server-Sent Events (token, artifact, status, done)
   v
FastAPI  --------------------------------------------------------------+
   | 1. validate + persist user message                                |
   | 2. router (qa | essay | artifact)                                 |
   | 3. retrieval: embed query (Ollama) -> pgvector top-k              |
   |       no evidence -> fixed "not covered" reply, NO model call     |
   | 4. build prompt: <sources> + history + request                    |
   | 5. Pi agent (subprocess, RPC mode) --> Ollama (local)  or  Claude |
   | 6. stream parse: text vs <artifact>, sanitize HTML, cite check    |
   | 7. persist assistant message + sources + artifact                 |
   v                                                                   |
PostgreSQL + pgvector  (episodes, chunks, sessions, messages)  <-------+
```

## 2. Components

| Component | File(s) | Responsibility |
|---|---|---|
| API | `backend/app/main.py` | Endpoints, validation, structured errors, SSE turn orchestration, health |
| Router | `router.py` | Deterministic intent classification, no LLM call |
| Retrieval | `retrieval.py`, `embeddings.py` | Query embedding, vector search, threshold, per-episode cap, sponsor filter |
| Ingestion | `ingest.py`, `chunking.py` | Parse transcripts (4 formats), chunk by speaker turn, embed, upsert by content hash |
| Agent layer | `agent.py`, `pi_agent/` | Spawns Pi in RPC mode; system prompt; Ship 30 skill; model config generated from `.env` |
| Artifacts | `artifacts.py` | Streaming tag parser, fallback salvage, HTML allow-list sanitizer |
| Persistence | `store.py`, `db.py` | Sessions, messages, schema |
| Frontend | `frontend/` | Chat, citations, sources, artifact viewer, sessions, theming |

## 3. Data model

```
episodes(slug PK, guest, title, youtube_url, publish_date, content_hash)
chunks(id PK, episode_slug FK, chunk_index, start_ts, content, embedding vector(768))   HNSW cosine index
sessions(id PK, title, user_meta jsonb, created_at, updated_at)
messages(id PK, session_id FK, role, content, route, provider, model, sources jsonb,
         artifact jsonb, latency_ms, created_at)
```
Re-running ingest skips unchanged episodes (SHA-256 of the file) and re-indexes changed ones atomically (one transaction per episode), which is the refresh path.

## 4. Why these choices

- **Pi in RPC mode as the agent layer.** Tiny system prompt (important for small local models), first-class Agent Skills (`/skill:ship30-essay` inlines the skill), and one interface for Ollama and Anthropic. One short-lived process per request; conversation state lives in Postgres, so sessions are independent and the agent is disposable.
- **Deterministic router.** Predictable, free, testable. Misrouting is limited to three obvious classes.
- **Evidence gate before the model.** If retrieval returns nothing above the threshold, the API answers with a fixed message and never calls the model. This guarantees "do not guess" for the common off-topic case.
- **Sentinel `NO_ANSWER`.** For the harder case (retrieved but irrelevant text), the model is told to reply with one code word; the API swaps in the same calm message. This avoids small models mixing a refusal with an answer (a real bug found during testing).
- **Pure-Python backend dependencies and no-build frontend.** On the target Windows laptop, Application Control blocked an unsigned compiled DLL. Removing compiled dependencies removed the failure class.
- **SSE over POST (fetch streaming).** Needs a request body; simple and proxy-friendly; keep-alive comments prevent idle timeouts during slow local prefill.

## 5. Request lifecycle details

1. Validate content (non-empty, length limit), session exists, provider available (409 otherwise).
2. Persist the user message first, so history survives failures.
3. Follow-ups ("turn that into a checklist") are detected by length/pronouns; the previous user question is added to the retrieval query and previously cited chunks are reused for artifact/essay routes.
4. Prompt = `<sources>` (numbered, trimmed to `MAX_SOURCE_CHARS`) + last N turns + request. Essay requests are prefixed with `/skill:ship30-essay`.
5. Stream: text deltas go to the client as `token`; `<artifact>` blocks are split out (tags may arrive split across tokens) and sent as `artifact_*` events; HTML is sanitized before the final event and before storage.
6. Done event carries latency, time to first token, grounding info (cited numbers, whether the answer had no citation) and the artifact.

## 6. API surface

`GET /health` · `GET /health/ready` (database, agent CLI, Ollama models, API key) · `GET /api/config` · `POST|GET /api/sessions` · `GET|DELETE /api/sessions/{id}` · `POST /api/sessions/{id}/messages` (SSE).
Errors share one shape: `{"error": {"code", "message", "details", "request_id"}}`.

## 7. Security

- Generated HTML: allow-list sanitizer (drops script, iframe, forms, event handlers, unsafe URLs, remote CSS) and a viewer iframe with `sandbox=""` (no scripts, no same-origin) plus CSP `default-src 'none'`.
- Markdown renderer escapes all HTML first and only emits its own tags; links limited to http(s)/mailto.
- Secrets only in `.env` (git-ignored); the API key is never sent to the browser.
- No authentication in v1 (non-goal); CORS limited to configured origins.

## 8. Failure modes and behavior

| Failure | Behavior |
|---|---|
| Ollama not running | `embedding_unavailable` or `model_error` with the exact fix ("open Ollama, check `ollama list`") |
| Model not pulled | Message naming the `ollama pull` command |
| Model too slow | Progress and elapsed time shown; timeouts (`FIRST_TOKEN_TIMEOUT_S`, `IDLE_TIMEOUT_S`, `TOTAL_TIMEOUT_S`) end the request with `model_timeout` |
| Cloud key missing | Cloud option disabled with the reason; 409 if forced |
| Cloud call fails | Retry once on Ollama and tell the user (`fallback` event) |
| Database down | 503 `database_unavailable` with the start command; `/health/ready` reports it |
| Retrieval empty | Fixed "not covered" reply, no model call |
| Model forgot artifact tags | Salvage fenced block or whole essay |
| Client disconnects | Generator closes, Pi process is terminated |
| Unexpected bug mid-stream | Caught; client receives an `error` event instead of a silent stream |

## 9. Configuration

All via `.env` (see `.env.example`): models (`OLLAMA_CHAT_MODEL`, `CLOUD_MODEL`), keys, thresholds (`MIN_SIMILARITY`, `TOP_K`, `MAX_SOURCE_CHARS`), timeouts, fallback flag. Pi's Ollama model list is regenerated from these values at runtime, so no code change is needed to switch models.

## 10. Observability

One JSON log line per event (request, retrieval with hit count and top similarity, agent errors, turn done with latency, time to first token and citation count). Every response carries `X-Request-ID`.

## 11. Search index portability and evaluation

Indexing is the slowest step (about 0.6 s per chunk on a CPU laptop), so the index can be exported to `seed/index.jsonl.gz` (base64 float32 vectors, lossless) and is imported automatically on first start when the database is empty. Import refuses a seed built with a different embedding model. `python -m app.eval` reports retrieval quality (hit@k, MRR, off-topic rejection) from a versioned case file, so quality claims are measurable and repeatable.

## 12. Known design trade-off: retrieval is not an agent tool

Retrieval runs in the API before the agent is called, and the agent runs with `--no-tools`. This is deliberate: small local models call tools unreliably, and a deterministic retrieve-then-generate flow guarantees the evidence gate. The cost is that the agent layer provides runtime, skills and model switching rather than autonomous tool use. A natural next step is exposing `search_transcripts` as a Pi tool and letting capable (cloud) models decide when to search.
