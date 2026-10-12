import logging

import httpx

from .config import settings

log = logging.getLogger("embeddings")


class EmbeddingError(RuntimeError):
    pass


def embed(texts: list[str], kind: str = "document") -> list[list[float]]:
    """Embed texts with Ollama. kind = 'document' or 'query' (nomic-embed-text uses task prefixes)."""
    prefix = "search_query: " if kind == "query" else "search_document: "
    try:
        r = httpx.post(
            f"{settings.ollama_base_url}/api/embed",
            json={"model": settings.embed_model, "input": [prefix + t for t in texts]},
            timeout=120,
        )
        r.raise_for_status()
    except httpx.ConnectError as e:
        raise EmbeddingError(
            f"Cannot reach Ollama at {settings.ollama_base_url}. Is Ollama running? (try: ollama list)"
        ) from e
    except httpx.HTTPStatusError as e:
        raise EmbeddingError(
            f"Ollama error {e.response.status_code}: {e.response.text[:200]} "
            f"(did you run: ollama pull {settings.embed_model} ?)"
        ) from e
    return r.json()["embeddings"]
