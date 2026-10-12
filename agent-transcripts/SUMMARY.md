# Build log: failures and how they were fixed

The full chat history of each AI session is saved next to this file (`claude-session-N.md`). This summary lists the important dead ends and corrections, in order.

| # | What went wrong | How it was found | Fix |
|---|---|---|---|
| 1 | Docker Desktop showed "Engine stopped" after install | Error screen and `wsl --status` said virtualization was not enabled | Enabled Virtual Machine Platform, updated WSL, restarted Windows |
| 2 | Pasted two commands on one line, then pasted the prompt text as a command | PowerShell parse errors | One command per line; copy only the command |
| 3 | `psycopg` crashed: "Application Control policy has blocked this file" | Traceback on first ingest | Replaced compiled drivers with pure-Python `pg8000`; removed `pgvector`/`pydantic-settings` from the backend; the vector is sent as text and cast in SQL |
| 4 | First ingest time estimate (20 to 40 minutes) was wrong | Measured 0.6 s per chunk (808 chunks in 497 s) | Full index would take about 5 hours, so added `--every N` sampling and indexed a spread sample; documented as a trade-off |
| 5 | 30 transcripts produced no chunks (different formats) | Warning `no chunks produced` for one episode, then a scan of all 303 | Parser now handles `Name (HH:MM:SS):`, `Name (MM:SS):`, `Name:` and `[HH:MM:SS] Name:` formats |
| 6 | One embedding request timed out | `ReadTimeout` in the ingest log; one episode skipped | Increased the timeout; re-run indexed only the missing episode (idempotent ingest) |
| 7 | Off-topic question ("best pizza topping") still returned results | Search test | Raised `MIN_SIMILARITY` from 0.45 to 0.70 using measured scores, then to 0.73 after the 19-question retrieval evaluation |
| 8 | Agent layer requirement missed in the first plan | Re-read the assignment line by line | Evaluated Claude Agent SDK vs Pi; chose Pi (small prompt, skills, RPC); verified it in a sandbox before integrating |
| 9 | Follow-up turns crashed silently (empty stream) | End-to-end test; log showed `Decimal is not JSON serializable` | Cast similarity to float; wrapped the stream so unexpected errors become an `error` event |
| 10 | CSS sanitizer only replaced keywords and left remote URLs in text | Failing unit test | Rewrote rules to remove whole `@import`, `url(...)`, `expression(...)` constructs |
| 11 | First real answer took 279 s | User run of the chat client | Measured that prompt reading dominated; reduced to 4 sources of 900 characters and switched to a 3B model: 40 to 61 s |
| 12 | 3B model refused and answered in the same message | Real UI test | Removed the quoted refusal sentence from the prompt; introduced the `NO_ANSWER` sentinel handled by the API; added a test |
| 13 | Citations placed mid-sentence by the 3B model | Real UI test | Added a style example and an explicit rule to the system prompt |
| 14 | Patch files copied to a wrong path because a shell variable was empty | PowerShell errors (`C:\backend\...`) | Used full paths; removed the stray folder |
| 15 | Risk that Windows would block a JS bundler's native binaries | Lesson from item 3 | Built the UI as plain HTML/CSS/ES modules with no build step |
| 16 | A fresh clone would have an empty index (indexing takes hours) | Reviewing the project as a reviewer would run it | Added `app.seed` export/import: `seed/index.jsonl.gz` loads automatically on first start (verified: about 50 s with Docker Compose) |
| 17 | Quality claims had no numbers | Same review | Added `app.eval` with 19 cases: hit@6 94%, MRR 0.91, off-topic rejection 100%; one miss documented |
| 18 | Essay requests retrieved the wrong sources | "Ship 30 for 30" and "essay" words polluted the search query | Added `clean_query()` to strip format words before retrieval, plus a dedicated essay prompt hint |
| 19 | Pi created `auth.json` and `models-store.json` inside the repo folder and they were committed | Reading the `git commit` file list before pushing | Removed them from the commit before the first push and added them to `.gitignore` |
| 20 | Essay on a 7B CPU model: about 650 words instead of 1,250 and about 6.5 minutes | Measured run | Documented as a limitation; essay generated before the demo; cloud model recommended |
