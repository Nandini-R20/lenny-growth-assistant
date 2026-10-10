# The Lenny Growth Assistant (work in progress: Day 1 = database + ingestion + retrieval)

## Prerequisites
Docker Desktop, Ollama (with `qwen2.5:7b` and `nomic-embed-text`), Python 3.11+, Git.

## Day 1 quick start (Windows PowerShell)
```powershell
# 1. Database
docker compose up -d

# 2. Transcripts (public dataset)
mkdir data
git clone --depth 1 https://github.com/ChatPRD/lennys-podcast-transcripts.git data/lennys-podcast-transcripts

# 3. Python env
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\.env.example .env

# 4. Tests, then index a few episodes, then search
python -m pytest -q
python -m app.ingest --limit 10
python -m app.search "How do you find product-market fit?"
```

## How retrieval works
Transcripts are split by speaker turn into ~300-word chunks (one-turn overlap), embedded with
`nomic-embed-text` via Ollama, and stored in Postgres + pgvector (HNSW cosine index). Each chunk keeps
episode, guest, YouTube URL and start timestamp, so answers can link to the exact moment.
If nothing scores above `MIN_SIMILARITY`, the search returns nothing and the assistant must say it doesn't know.
