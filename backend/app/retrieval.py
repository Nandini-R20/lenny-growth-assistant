from dataclasses import dataclass

from .config import settings
from .db import connect, run, vec
from .embeddings import embed


@dataclass
class Hit:
    slug: str
    guest: str
    title: str
    youtube_url: str
    start_ts: str
    content: str
    similarity: float

    @property
    def link(self) -> str:
        """Deep link to the moment in the YouTube video."""
        if not self.start_ts:  # some episodes have no timestamps
            return self.youtube_url
        h, m, s = (int(x) for x in self.start_ts.split(":"))
        return f"{self.youtube_url}&t={h * 3600 + m * 60 + s}s"


def search(question: str, k: int | None = None) -> list[Hit]:
    """Return the top-k most relevant chunks above the similarity threshold.
    An empty list means 'the transcripts do not support an answer'."""
    k = k or settings.top_k
    qvec = vec(embed([question], kind="query")[0])
    conn = connect()
    try:
        rows = run(conn, """
            SELECT e.slug, e.guest, e.title, e.youtube_url, c.start_ts, c.content,
                   1 - (c.embedding <=> %s::vector) AS sim
            FROM chunks c JOIN episodes e ON e.slug = c.episode_slug
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
            """, (qvec, qvec, k)).fetchall()
    finally:
        conn.close()
    hits = [Hit(*r) for r in rows]
    return [h for h in hits if h.similarity >= settings.min_similarity]
