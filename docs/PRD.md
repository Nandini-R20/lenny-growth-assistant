# PRD: The Lenny Growth Assistant

Status: v1 (take-home build) · Author: candidate · Date: 10 Oct 2026

## 1. Discovery brief

**Customer (assumed).** A product or growth team at an early-stage startup (a Head of Growth, a PM, a founder) that already uses Lenny's Podcast as a source of practical advice and wants answers they can trust and act on.

**Problem.** The advice exists, but it is buried in about 300 long episodes. Finding "what did people actually say about hiring a head of growth?" today means searching YouTube, skimming hour-long videos, or asking a general chatbot that answers confidently without evidence. The cost is time, and the bigger risk is acting on advice that was paraphrased wrongly or never said.

**Insight.** Trust, not fluency, is the missing feature. A useful assistant must (1) answer only from the archive, (2) show exactly where each claim came from, down to the minute, and (3) say "not covered" instead of guessing. After that, it should turn answers into things people reuse: a checklist, a one-pager, a ready-to-publish essay.

**Jobs to be done.**
1. "Give me the advice from the people who have done this, with receipts."
2. "Turn what we just discussed into something I can share with my team."
3. "Draft a post from this material in a proven writing format (Ship 30 for 30)."

**Why now.** Small local models plus vector search make a private, low-cost, grounded assistant feasible on a laptop, and agent runtimes with skills make the writing workflow reusable.

## 2. Goals and non-goals

Goals (v1): grounded Q&A with citations; follow-up questions in a chat; Ship 30 essays; Markdown/HTML artifacts in a safe viewer; local-first with an optional cloud model; one-command startup.

Non-goals (v1): accounts and authentication; multi-user sharing; streaming audio or video; fine-tuning; indexing sources other than the transcripts; mobile app.

## 3. Success metrics

North star: **Grounded answer rate**, the share of answers where every substantive claim carries a valid citation that opens the right episode moment. Target: at least 90% on a fixed set of 30 test questions (reviewed by hand; the manual plan in `docs/test-plan.md` defines the method).

Supporting metrics:
| Metric | Target | How measured |
|---|---|---|
| Unsupported-question handling | 100% of off-topic questions answered with "not covered" and no model call | automated test + manual cases M-04, M-05 |
| Time to first word (local, CPU laptop) | under 45 s with the 3B model | `ttft_ms` in every response and log line |
| Time to first word (cloud) | under 5 s | same |
| Citation validity | 0 citations pointing to a source number that was not provided | `grounding.cited` check in the API |
| Reliability | 0 unhandled crashes in the manual plan; every failure shows a clear message | cases M-10 to M-14 |

## 4. Scope (what v1 does)

Chat with sessions; routing between answer, essay and artifact; retrieval over pgvector with a similarity threshold, per-episode cap and sponsor-read filter; Pi agent runtime with Ollama (default) or Claude; Ship 30 skill; artifact viewer with sanitization and sandbox; health endpoints, structured logs, and a Docker Compose startup.

## 5. Assumptions

1. The public transcript dataset is accurate enough to quote; speaker labels and timestamps are mostly reliable (30 of 303 files use different formats, handled by the parser).
2. Users will accept a slower answer on local models if it is private and free; a cloud option covers impatient users (the cloud path is implemented and its fallback tested, but it was not tested with a real API key).
3. A similarity threshold of 0.73 separates relevant from irrelevant questions well enough for v1 (measured, see section 6; tuned on 19 questions, so the margin is thin).
4. Indexing a spread sample (every 4th episode plus the first 10) is a good v1 trade-off; the system supports indexing all 303 later with one command.
5. The reader will check citations, so showing the quote and a deep link beats polishing prose.

## 6. Evidence gathered while building

- Relevant questions scored about 0.73 to 0.80 top similarity; off-topic questions scored at most about 0.66 to 0.70. The threshold started at 0.45 (too permissive), moved to 0.70, and is now 0.73 after the evaluation below.
- Retrieval evaluation (`python -m app.eval`, 19 cases, details in `docs/eval-results.md`): hit@6 = 94% (15 of 16 on-topic), MRR = 0.91, off-topic rejection = 100% (3 of 3). One known miss: "product discovery with customers".
- One-command startup was verified with Docker Compose: an empty database loads the bundled index (`seed/index.jsonl.gz`, 82 episodes, 8,181 chunks) automatically in about 50 seconds.
- Indexing speed on the target laptop was about 0.6 s per chunk. Full index (30,101 chunks) would take about 5 hours, so a sample was indexed (82 episodes, about 8,200 chunks).
- Answer latency: 7B model with 6 long sources took 279 s; 3B with 4 short sources took 40 to 61 s. Prompt size, not generation, dominated on CPU.

## 7. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Small local model invents details | Wrong advice | Strict system prompt, citation on every claim, quote cards beside every answer, "not covered" path, cloud option |
| Off-topic question gets a confident answer | Trust loss | Deterministic no-evidence path before the model; sentinel `NO_ANSWER` when the model judges sources irrelevant |
| Generated HTML is malicious | Security | Server allow-list sanitizer + sandboxed iframe with no scripts and a strict CSP |
| Slow local answers | Bad demo/UX | Prompt size knobs, 3B or 7B choice, visible progress, cloud toggle, stop button. Measured on CPU: 7B essay takes about 6.5 minutes and came out about 650 words (target 1,250), so essays are generated ahead of demos |
| Essay faithfulness slips with small models | Subtle misstatements | Example found: "interns" where the transcript says "earlier in career". Mitigation: every claim is cited so a reader can check; cloud model recommended for essays |
| Index covers only part of the archive | Missed answers | State the coverage in the UI ("82 episodes indexed"); one-command full ingest |
| Cloud outage or missing key | Failed request | Cloud option disabled with reason; automatic fallback to local with a visible notice |
| Platform security tools block binaries (observed on Windows) | Setup failure | Pure-Python backend dependencies and a no-build frontend |

## 8. Open questions

Should the index cover all episodes before launch? Do users want exports (PDF/Docx)? Is a hybrid keyword + vector search worth the complexity (names such as "Todd Jackson" benefit from keyword match)?

## 9. Rollout

v1: internal demo on a laptop via Docker Compose. v1.1: full index, hybrid search, auth. v2: team sharing and saved artifacts.
