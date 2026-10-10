"""Settings come from environment variables or a .env file, so DB/models can be switched without code changes.
(Plain Python on purpose: no compiled dependencies.)"""
import os
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


class Settings:
    def __init__(self) -> None:
        env = os.environ.get
        self.database_url = env("DATABASE_URL", "postgresql://lenny:lenny@localhost:5433/lenny")
        self.ollama_base_url = env("OLLAMA_BASE_URL", "http://localhost:11434")
        self.embed_model = env("EMBED_MODEL", "nomic-embed-text")
        self.embed_dim = int(env("EMBED_DIM", "768"))
        self.transcripts_dir = env("TRANSCRIPTS_DIR", "../data/lennys-podcast-transcripts/episodes")
        self.top_k = int(env("TOP_K", "6"))
        self.min_similarity = float(env("MIN_SIMILARITY", "0.45"))


settings = Settings()
