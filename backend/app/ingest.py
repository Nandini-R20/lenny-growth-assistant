"""Load transcripts -> chunk -> embed -> store in Postgres.

Run:  python -m app.ingest --limit 20     (quick test)
      python -m app.ingest                (all episodes)
Re-running is safe: unchanged episodes are skipped (content hash), changed ones are re-indexed.
"""
import argparse
import hashlib
import logging
import time
from pathlib import Path

import frontmatter

from .chunking import chunk_transcript
from .config import settings
from .db import connect, init_schema, run, vec
from .embeddings import embed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ingest")

BATCH = 16


def ingest_episode(conn, path: Path) -> int:
    slug = path.parent.name
    raw = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(raw.encode()).hexdigest()

    row = run(conn, "SELECT content_hash FROM episodes WHERE slug=%s", (slug,)).fetchone()
    conn.commit()
    if row and row[0] == digest:
        log.info("skip (unchanged): %s", slug)
        return 0

    post = frontmatter.loads(raw)
    meta = post.metadata
    chunks = chunk_transcript(post.content)
    if not chunks:
        log.warning("no chunks produced for %s", slug)
        return 0

    vectors: list[list[float]] = []
    for i in range(0, len(chunks), BATCH):
        vectors += embed([c.text for c in chunks[i:i + BATCH]], kind="document")

    try:  # one transaction per episode: all-or-nothing
        run(conn, "DELETE FROM episodes WHERE slug=%s", (slug,))  # cascades to chunks
        run(conn,
            "INSERT INTO episodes (slug, guest, title, youtube_url, publish_date, content_hash) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (slug, meta.get("guest"), meta.get("title"), meta.get("youtube_url"),
             str(meta.get("publish_date")) if meta.get("publish_date") else None, digest))
        for c, v in zip(chunks, vectors):
            run(conn,
                "INSERT INTO chunks (episode_slug, chunk_index, start_ts, content, embedding) "
                "VALUES (%s,%s,%s,%s,%s::vector)",
                (slug, c.index, c.start_ts, c.text, vec(v)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    log.info("indexed %s: %d chunks", slug, len(chunks))
    return len(chunks)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="only first N episodes (for quick tests)")
    ap.add_argument("--every", type=int, default=None,
                    help="take every Nth episode (spread sample, e.g. --every 4 = ~76 episodes)")
    args = ap.parse_args()

    root = Path(settings.transcripts_dir)
    files = sorted(root.glob("*/transcript.md"))
    if not files:
        raise SystemExit(f"No transcripts found in {root.resolve()}. Did you clone the repo into data/ ?")
    if args.every:
        files = files[:: args.every]
    if args.limit:
        files = files[: args.limit]

    init_schema()
    t0, total = time.time(), 0
    conn = connect(autocommit=False)
    try:
        for n, f in enumerate(files, 1):
            log.info("[%d/%d] %s", n, len(files), f.parent.name)
            try:
                total += ingest_episode(conn, f)
            except Exception:
                log.exception("failed on %s (continuing)", f.parent.name)
    finally:
        conn.close()
    log.info("done: %d new chunks in %.0fs", total, time.time() - t0)


if __name__ == "__main__":
    main()
