import re
from dataclasses import dataclass

from .config import settings
from .db import connect, run, vec
from .embeddings import embed

# Sponsor reads are noise for grounding. Drop a chunk only when it has 2+ ad markers.
AD_MARKERS = re.compile(
    r"brought to you by|sponsored by|use (the )?code\b|promo code|offer code|"
    r"free trial|head (on )?over to \w+\.com|\.com/lenny|visit \w+\.com",
    re.I,
)


@dataclass
class Hit:
    chunk_id: int
    slug: str
    guest: str
    title: str
    youtube_url: str
    start_ts: str
    content: str
    similarity: float

    def __post_init__(self):
        self.similarity = float(self.similarity)  # drivers may return Decimal

    @property
    def link(self) -> str:
        """Deep link to the moment in the YouTube video."""
        if not self.start_ts:  # some episodes have no timestamps
            return self.youtube_url
        h, m, s = (int(x) for x in self.start_ts.split(":"))
        return f"{self.youtube_url}&t={h * 3600 + m * 60 + s}s"


def is_ad(text: str) -> bool:
    return len(AD_MARKERS.findall(text)) >= 2


def search(question: str, k: int | None = None, per_episode: int = 2) -> list[Hit]:
    """Top-k relevant chunks above the similarity threshold, max `per_episode` per episode,
    sponsor reads removed. An empty list means 'the transcripts do not support an answer'."""
    k = k or settings.top_k
    qvec = vec(embed([question], kind="query")[0])
    conn = connect()
    try:
        rows = run(conn, """
            SELECT c.id, e.slug, e.guest, e.title, e.youtube_url, c.start_ts, c.content,
                   1 - (c.embedding <=> %s::vector) AS sim
            FROM chunks c JOIN episodes e ON e.slug = c.episode_slug
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
            """, (qvec, qvec, k * 5)).fetchall()
    finally:
        conn.close()
    hits, per_ep = [], {}
    for r in rows:
        h = Hit(*r)
        if h.similarity < settings.min_similarity or is_ad(h.content):
            continue
        if per_ep.get(h.slug, 0) >= per_episode:
            continue
        per_ep[h.slug] = per_ep.get(h.slug, 0) + 1
        hits.append(h)
        if len(hits) >= k:
            break
    return hits


def hits_by_ids(ids: list[int]) -> list[Hit]:
    """Re-load chunks cited earlier in the conversation (used for follow-ups like 'turn that into a checklist')."""
    if not ids:
        return []
    conn = connect()
    try:
        rows = run(conn, """
            SELECT c.id, e.slug, e.guest, e.title, e.youtube_url, c.start_ts, c.content, 1.0::float8
            FROM chunks c JOIN episodes e ON e.slug = c.episode_slug
            WHERE c.id = ANY(%s)""", (list(ids),)).fetchall()
    finally:
        conn.close()
    order = {i: n for n, i in enumerate(ids)}
    return sorted((Hit(*r) for r in rows), key=lambda h: order[h.chunk_id])
