import logging
from urllib.parse import urlparse

import pg8000.dbapi

from .config import settings

log = logging.getLogger("db")


def connect(autocommit: bool = True):
    """Open a Postgres connection (pure-Python driver)."""
    u = urlparse(settings.database_url)
    conn = pg8000.dbapi.connect(
        user=u.username, password=u.password, host=u.hostname,
        port=u.port or 5432, database=u.path.lstrip("/"),
    )
    conn.autocommit = autocommit
    return conn


def vec(v: list[float]) -> str:
    """pgvector accepts the text form '[0.1,0.2,...]' (cast with ::vector in SQL)."""
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def run(conn, sql: str, params: tuple = ()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def init_schema() -> None:
    """Create extension + tables + vector index (idempotent)."""
    conn = connect()
    try:
        run(conn, "CREATE EXTENSION IF NOT EXISTS vector")
        run(conn, """
            CREATE TABLE IF NOT EXISTS episodes (
                slug         TEXT PRIMARY KEY,
                guest        TEXT,
                title        TEXT,
                youtube_url  TEXT,
                publish_date DATE,
                content_hash TEXT NOT NULL
            )""")
        run(conn, f"""
            CREATE TABLE IF NOT EXISTS chunks (
                id           BIGSERIAL PRIMARY KEY,
                episode_slug TEXT NOT NULL REFERENCES episodes(slug) ON DELETE CASCADE,
                chunk_index  INT NOT NULL,
                start_ts     TEXT,
                content      TEXT NOT NULL,
                embedding    vector({settings.embed_dim}) NOT NULL
            )""")
        run(conn, "CREATE INDEX IF NOT EXISTS chunks_embedding_idx "
                  "ON chunks USING hnsw (embedding vector_cosine_ops)")
        run(conn, "CREATE INDEX IF NOT EXISTS chunks_episode_idx ON chunks(episode_slug)")
        run(conn, """
            CREATE TABLE IF NOT EXISTS sessions (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL DEFAULT 'New chat',
                user_meta  JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")
        run(conn, """
            CREATE TABLE IF NOT EXISTS messages (
                id         BIGSERIAL PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role       TEXT NOT NULL CHECK (role IN ('user','assistant')),
                content    TEXT NOT NULL,
                route      TEXT,
                provider   TEXT,
                model      TEXT,
                sources    JSONB NOT NULL DEFAULT '[]'::jsonb,
                artifact   JSONB,
                latency_ms INT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")
        run(conn, "CREATE INDEX IF NOT EXISTS messages_session_idx ON messages(session_id, id)")
    finally:
        conn.close()
    log.info("schema ready")
