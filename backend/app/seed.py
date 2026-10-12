"""Portable search index: export the indexed episodes + vectors to one file, import them on a fresh machine.

Why: indexing needs hours of CPU time with the embedding model. A reviewer who clones the repo should get a
working assistant in minutes, so the repo ships `seed/index.jsonl.gz` and the app imports it on first start
when the database is empty. Vectors are stored as base64 float32 (lossless), so search behaves identically.

  python -m app.seed export      # after you have indexed episodes
  python -m app.seed import      # manual import (also happens automatically on first start)
"""
import argparse
import array
import base64
import gzip
import json
import logging
from pathlib import Path

from .config import settings
from .db import connect, init_schema, run, vec

log = logging.getLogger("seed")
FORMAT_VERSION = 1


class SeedError(RuntimeError):
    pass


def pack_vector(vector_text: str) -> str:
    """'[0.1,0.2,...]' (pgvector text) -> base64 of little-endian float32."""
    a = array.array("f", json.loads(vector_text))
    return base64.b64encode(a.tobytes()).decode("ascii")


def unpack_vector(b64: str) -> list[float]:
    a = array.array("f")
    a.frombytes(base64.b64decode(b64))
    return a.tolist()


def export_seed(path: str | Path | None = None) -> Path:
    out = Path(path or settings.seed_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    conn = connect()
    n_ep = n_ch = 0
    try:
        with gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as f:
            f.write(json.dumps({"type": "meta", "version": FORMAT_VERSION, "model": settings.embed_model,
                                "dim": settings.embed_dim}) + "\n")
            for r in run(conn, "SELECT slug, guest, title, youtube_url, publish_date, content_hash "
                               "FROM episodes ORDER BY slug").fetchall():
                f.write(json.dumps({"type": "episode", "slug": r[0], "guest": r[1], "title": r[2], "url": r[3],
                                    "date": str(r[4]) if r[4] else None, "hash": r[5]}) + "\n")
                n_ep += 1
            cur = run(conn, "SELECT episode_slug, chunk_index, start_ts, content, embedding::text "
                            "FROM chunks ORDER BY episode_slug, chunk_index")
            for r in iter(cur.fetchone, None):
                f.write(json.dumps({"type": "chunk", "slug": r[0], "i": r[1], "ts": r[2], "text": r[3],
                                    "emb": pack_vector(r[4])}) + "\n")
                n_ch += 1
    finally:
        conn.close()
    log.info("seed exported", extra={"episodes": n_ep, "chunks": n_ch, "path": str(out),
                                     "mb": round(out.stat().st_size / 1e6, 1)})
    return out


def import_seed(path: str | Path | None = None) -> dict:
    src = Path(path or settings.seed_path)
    if not src.exists():
        raise SeedError(f"Seed file not found: {src}")
    with gzip.open(src, "rt", encoding="utf-8") as f:
        meta = json.loads(f.readline())
        if meta.get("type") != "meta" or meta.get("version") != FORMAT_VERSION:
            raise SeedError("Unsupported seed file format.")
        if meta.get("model") != settings.embed_model or meta.get("dim") != settings.embed_dim:
            raise SeedError(f"The seed was built with {meta.get('model')} ({meta.get('dim')} dims) but this app uses "
                            f"{settings.embed_model} ({settings.embed_dim}). Re-run ingestion instead.")
        init_schema()
        conn = connect(autocommit=False)
        added_eps: set[str] = set()
        n_ch = 0
        try:
            existing = {r[0] for r in run(conn, "SELECT slug FROM episodes").fetchall()}
            for line in f:
                rec = json.loads(line)
                if rec["type"] == "episode" and rec["slug"] not in existing:
                    run(conn, "INSERT INTO episodes (slug, guest, title, youtube_url, publish_date, content_hash) "
                              "VALUES (%s,%s,%s,%s,%s,%s)",
                        (rec["slug"], rec["guest"], rec["title"], rec["url"], rec["date"], rec["hash"]))
                    added_eps.add(rec["slug"])
                elif rec["type"] == "chunk" and rec["slug"] in added_eps:
                    run(conn, "INSERT INTO chunks (episode_slug, chunk_index, start_ts, content, embedding) "
                              "VALUES (%s,%s,%s,%s,%s::vector)",
                        (rec["slug"], rec["i"], rec["ts"], rec["text"], vec(unpack_vector(rec["emb"]))))
                    n_ch += 1
                    if n_ch % 500 == 0:
                        conn.commit()
                        log.info("seed progress", extra={"chunks": n_ch})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    log.info("seed imported", extra={"episodes": len(added_eps), "chunks": n_ch})
    return {"episodes": len(added_eps), "chunks": n_ch}


def _count_episodes() -> int:
    conn = connect()
    try:
        return run(conn, "SELECT count(*) FROM episodes").fetchone()[0]
    finally:
        conn.close()


def seed_if_empty() -> dict | None:
    """Called on app start: import the bundled index when the database has no episodes yet."""
    try:
        if _count_episodes() > 0 or not Path(settings.seed_path).exists():
            return None
        log.info("empty index: importing bundled seed", extra={"path": settings.seed_path})
        return import_seed()
    except Exception as e:  # never block startup
        log.error("seed import failed", extra={"error": str(e)})
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["export", "import"])
    ap.add_argument("--path", default=None)
    a = ap.parse_args()
    if a.action == "export":
        print("wrote", export_seed(a.path))
    else:
        print(import_seed(a.path))


if __name__ == "__main__":
    import logging as _l
    from .logging_setup import setup
    setup("INFO")
    main()
