# Test plan

## 1. Automated tests

Run: `cd backend && python -m pytest -q` (the API tests need `docker compose up -d db`; they skip automatically if the database is down) and `node frontend/lib.test.mjs`.

| Area | What is covered | File |
|---|---|---|
| Chunking | speaker turns, timestamps (3 formats), no-timestamp files, inline `[00:00:12] Name:` format, overlap, size bounds, empty input | `tests/test_chunking.py` |
| Routing | question vs essay vs artifact examples, follow-up detection | `tests/test_router.py` |
| Artifacts | split tags across tokens, missing close tag, salvage of fenced blocks and whole essays, sanitizer (scripts, handlers, unsafe links, svg, forms, comments, remote CSS), text escaping | `tests/test_artifacts.py` |
| Prompting and retrieval helpers | essay prompt forces the skill, sources numbered, history, sponsor filter, deep links | `tests/test_prompts_retrieval.py` |
| API (agent and retrieval faked, real Postgres) | grounded answer + citations + persistence; no-evidence answer never calls the model; HTML artifact sanitized and stored; essay uses the skill; follow-up carries history; sessions independent; cloud failure falls back to local; model timeout is a structured error; validation and error contracts (422, 404, 409); delete session; `NO_ANSWER` sentinel | `tests/test_api.py` |
| Frontend helpers | markdown XSS safety, citation chips, link scheme blocking, tables, SSE parser with split frames, timestamp formatting | `frontend/lib.test.mjs` |

Current result: 49 Python tests and 15 JS checks pass. Retrieval quality: `python -m app.eval --write` (results in `docs/eval-results.md`). Also verified in a headless browser: page loads without script errors, streaming, popover, sandboxed iframe, history reload, dark mode and mobile layout.

Not covered by automation (stated honestly): real-model answer quality, Docker image build, Windows-specific behavior. These are in the manual plan.

## 2. Manual UI test plan

Preconditions: Docker running, Ollama running with the models pulled, app open at http://localhost:8000.

| ID | Steps | Expected |
|---|---|---|
| M-01 | Open the app | Headline, four example prompts, model toggle shows Local with the model id, sidebar shows "N episodes indexed" |
| M-02 | Ask "How do you hire a head of growth?" | Phase text and elapsed seconds while waiting; answer streams; citation chips at sentence ends; 4 source cards with timestamps; meta line with model and times |
| M-03 | Hover a chip, click it | Popover with guest, episode, quote; click opens YouTube near the timestamp |
| M-04 | Ask "What is the best pizza topping?" | Calm "transcripts don't cover that" card with suggestions; no source cards |
| M-05 | Ask a nonsense string | Same as M-04 |
| M-06 | After M-02 ask "Turn that into a checklist" | Viewer opens, writes live, switches to Preview, chip appears in chat |
| M-07 | In the viewer: Source tab, Copy, Download | Source shown; copy works; file downloads with a sensible name |
| M-08 | Ask "Make an HTML page for this" | HTML preview in an iframe; note lists anything removed; no scripts run |
| M-09 | Ask "Write an essay on hiring your first head of growth" | Essay in the viewer: headline, hook, subheaded points, takeaway, sources list; about 1,100 to 1,400 words; claims cited |
| M-10 | Stop Ollama, ask a question | Clear message saying Ollama is unreachable and how to fix it; Try again works after restarting |
| M-11 | Click Stop during a long answer | Streaming stops; no error; chat remains usable |
| M-12 | Stop the database container, send a message | Clear database message; `/health/ready` reports degraded |
| M-13 | Choose Cloud without a key | Option is disabled with the reason |
| M-14 | With a bad key, choose Cloud | Notice that cloud failed and the answer came from the local model |
| M-15 | Create 2 chats, switch, reload the page, delete one | Histories independent and restored; delete removes it |
| M-16 | Switch theme; narrow the window to 380 px | Both themes readable; layout single-column with working menu and viewer overlay |
| M-17 | Paste a 5,000-character message | Input limit prevents it; API would answer 422 |

Grounding review (supports the north-star metric): ask 30 questions, open each citation, mark each claim supported or not, compute the share of fully supported answers. Record results in `docs/grounding-review.md` before submission.
