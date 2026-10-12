"""Settings come from environment variables or a .env file, so DB/models can be switched without code changes.
(Plain Python on purpose: no compiled dependencies.)"""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


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
        self.top_k = int(env("TOP_K", "4"))
        self.min_similarity = float(env("MIN_SIMILARITY", "0.73"))
        self.seed_path = env("SEED_PATH", str(BACKEND_DIR.parent / "seed" / "index.jsonl.gz"))
        self.max_source_chars = int(env("MAX_SOURCE_CHARS", "900"))  # smaller = faster on CPU
        # --- agent / model configuration (switch models by editing .env, no code change) ---
        self.default_provider = env("DEFAULT_PROVIDER", "ollama")  # "ollama" | "anthropic"
        self.ollama_chat_model = env("OLLAMA_CHAT_MODEL", "qwen2.5:7b")
        self.anthropic_api_key = env("ANTHROPIC_API_KEY", "")
        self.cloud_model = env("CLOUD_MODEL", "claude-haiku-5-5")
        self.fallback_to_local = env("FALLBACK_TO_LOCAL", "true").lower() == "true"
        self.pi_bin = env("PI_BIN", "pi")
        self.pi_agent_dir = env("PI_AGENT_DIR", str(BACKEND_DIR / "pi_agent"))
        # --- limits / timeouts (seconds) ---
        self.first_token_timeout = int(env("FIRST_TOKEN_TIMEOUT_S", "300"))
        self.idle_timeout = int(env("IDLE_TIMEOUT_S", "120"))
        self.total_timeout = int(env("TOTAL_TIMEOUT_S", "1500"))
        self.history_turns = int(env("HISTORY_TURNS", "6"))
        self.max_message_chars = int(env("MAX_MESSAGE_CHARS", "4000"))
        self.cors_origins = [o.strip() for o in env("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if o.strip()]
        self.log_level = env("LOG_LEVEL", "INFO")


settings = Settings()
