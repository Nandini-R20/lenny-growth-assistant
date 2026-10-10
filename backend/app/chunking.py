"""Turn a transcript into retrievable chunks.

Transcript body looks like:
    Lenny (00:00:00):
    You were basically the 10th engineer ...

    Boz (00:00:12):
    Yeah ...

We split by speaker turn (so we never cut a sentence in half), then pack
consecutive turns into ~TARGET_WORDS chunks, overlapping by one turn so an
idea that straddles a boundary is still retrievable. Each chunk remembers the
timestamp where it starts, so answers can point to a moment in the episode.
"""
import re
from dataclasses import dataclass

TARGET_WORDS = 280
MAX_WORDS = 400

# Turn headers come in a few shapes across episodes:
#   "Lenny (00:00:12):"   "Lenny (00:12):"   "Lenny:"   and a bare "(00:13):" (same speaker continues)
_T = r"\d{1,2}:\d{2}(?::\d{2})?"
TURN_RE = re.compile(
    rf"^(?:(?P<speaker>[^\n(:]{{1,60}}?)(?: \((?P<ts>{_T})\))?|\((?P<ts2>{_T})\)):[ \t]*$", re.M
)


INLINE_RE = re.compile(rf"^\[(?P<ts>{_T})\] (?P<speaker>[^:\n]{{1,60}}):[ \t]*", re.M)


def _norm_ts(ts: str) -> str:
    """'00:13' -> '00:00:13' so every timestamp is H:MM:SS."""
    if not ts:
        return ""
    return ts if ts.count(":") == 2 else "00:" + ts


@dataclass
class Chunk:
    index: int
    start_ts: str
    text: str


def _split_turns(body: str) -> list[tuple[str, str, str]]:
    """Return [(speaker, timestamp, text)] for each speaker turn."""
    matches = list(TURN_RE.finditer(body))
    turns = []
    last_speaker = "Speaker"
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = body[m.end():end].strip()
        speaker = (m.group("speaker") or "").strip() or last_speaker
        last_speaker = speaker
        if text:
            turns.append((speaker, _norm_ts(m.group("ts") or m.group("ts2") or ""), text))
    return turns


def _split_long(text: str, max_words: int) -> list[str]:
    """A single monologue can be huge; split it on sentence boundaries."""
    words = text.split()
    if len(words) <= max_words:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    parts, cur, n = [], [], 0
    for s in sentences:
        w = len(s.split())
        if cur and n + w > max_words:
            parts.append(" ".join(cur))
            cur, n = [], 0
        cur.append(s)
        n += w
    if cur:
        parts.append(" ".join(cur))
    return parts


def chunk_transcript(body: str) -> list[Chunk]:
    if "## Transcript" in body:
        body = body.split("## Transcript", 1)[1]
    # One more shape: "[00:00:28] Lenny: text on the same line" -> rewrite into the header form
    body = INLINE_RE.sub(lambda m: f"{m.group('speaker').strip()} ({m.group('ts')}):\n", body)

    pieces: list[tuple[str, str]] = []  # (timestamp, "Speaker: text")
    for speaker, ts, text in _split_turns(body):
        for part in _split_long(text, MAX_WORDS):
            pieces.append((ts, f"{speaker}: {part}"))

    chunks: list[Chunk] = []
    cur: list[tuple[str, str]] = []
    words = 0
    for ts, line in pieces:
        w = len(line.split())
        if cur and words + w > TARGET_WORDS:
            chunks.append(Chunk(len(chunks), cur[0][0], "\n".join(l for _, l in cur)))
            cur = cur[-1:]  # one-turn overlap
            words = len(cur[0][1].split())
        cur.append((ts, line))
        words += w
    if cur:
        chunks.append(Chunk(len(chunks), cur[0][0], "\n".join(l for _, l in cur)))
    return chunks
