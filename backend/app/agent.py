"""Agent layer: drives the Pi coding agent (https://pi.dev) in RPC mode as a subprocess.

Why Pi: minimal system prompt (good for small local models), first-class Agent Skills
(the Ship 30 skill is a real SKILL.md), and one interface for both Ollama and Anthropic.

Each request starts a short-lived `pi --mode rpc --no-session` process (about 0.5 s).
Conversation state is owned by PostgreSQL, not by the agent, so sessions stay independent and
the agent process is disposable. Everything here is synchronous on purpose: blocking pipes read
in a thread, no dependency on the asyncio event-loop type (which differs on Windows).
"""
import json
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Iterator

from .config import settings

log = logging.getLogger("agent")


class AgentError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False, partial: bool = False):
        super().__init__(message)
        self.code, self.message, self.retryable, self.partial = code, message, retryable, partial


def provider_status() -> list[dict]:
    """What the UI toggle shows. Cloud is only 'available' when a key is configured."""
    cloud_ok = bool(settings.anthropic_api_key)
    return [
        {"id": "ollama", "label": "Local (Ollama)", "model": settings.ollama_chat_model,
         "available": True, "reason": None},
        {"id": "anthropic", "label": "Cloud (Claude)", "model": settings.cloud_model,
         "available": cloud_ok, "reason": None if cloud_ok else "ANTHROPIC_API_KEY is not set"},
    ]


def model_for(provider: str) -> str:
    return settings.cloud_model if provider == "anthropic" else settings.ollama_chat_model


def ensure_models_json() -> None:
    """Keep Pi's Ollama endpoint/model in sync with .env (so switching models needs no code change)."""
    base = settings.ollama_base_url.rstrip("/") + "/v1"
    models = [{"id": settings.ollama_chat_model}]
    cfg = {"providers": {"ollama": {"baseUrl": base, "api": "openai-completions",
                                    "apiKey": "ollama", "models": models}}}
    path = Path(settings.pi_agent_dir) / "models.json"
    new = json.dumps(cfg, indent=2) + "\n"
    try:
        if not path.exists() or path.read_text(encoding="utf-8") != new:
            path.write_text(new, encoding="utf-8")
    except OSError:
        log.warning("could not write models.json", extra={"path": str(path)})


def pi_path() -> str | None:
    return shutil.which(settings.pi_bin)


class PiAgent:
    """Streams assistant text deltas for one prompt."""

    def stream(self, provider: str, message: str) -> Iterator[str | None]:
        """Yields text deltas; yields None as a heartbeat while waiting (so the HTTP stream stays alive)."""
        exe = pi_path()
        if not exe:
            raise AgentError("agent_unavailable",
                             "The Pi agent CLI was not found. Install it with: "
                             "npm install -g --ignore-scripts @earendil-works/pi-coding-agent")
        if provider == "anthropic" and not settings.anthropic_api_key:
            raise AgentError("provider_unavailable", "ANTHROPIC_API_KEY is not set, so the cloud model is unavailable.")
        ensure_models_json()
        model = model_for(provider)
        env = {**os.environ, "PI_CODING_AGENT_DIR": settings.pi_agent_dir, "PI_OFFLINE": "1"}
        if settings.anthropic_api_key:
            env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
        cmd = [exe, "--mode", "rpc", "--no-session", "--no-tools", "--no-context-files",
               "--no-extensions", "--no-mcp", "--provider", provider, "--model", model]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, env=env, cwd=settings.pi_agent_dir)
        except OSError as e:
            raise AgentError("agent_unavailable", f"Could not start the Pi agent: {e}") from e

        lines: "queue.Queue[bytes | None]" = queue.Queue()
        stderr_tail: list[str] = []

        def pump_stdout():
            for line in iter(proc.stdout.readline, b""):
                lines.put(line)
            lines.put(None)

        def pump_stderr():
            for line in iter(proc.stderr.readline, b""):
                stderr_tail.append(line.decode("utf-8", "replace").rstrip())
                del stderr_tail[:-20]

        threading.Thread(target=pump_stdout, daemon=True).start()
        threading.Thread(target=pump_stderr, daemon=True).start()

        started, got_token, last_error = time.monotonic(), False, None
        try:
            proc.stdin.write(json.dumps({"id": "p1", "type": "prompt", "message": message}).encode() + b"\n")
            proc.stdin.flush()
            while True:
                limit = settings.idle_timeout if got_token else settings.first_token_timeout
                remaining = min(limit, settings.total_timeout - (time.monotonic() - started))
                if remaining <= 0:
                    raise AgentError("model_timeout",
                                     f"The {provider} model took too long to respond (over {limit}s). "
                                     "Try a shorter request or a smaller model.", retryable=True, partial=got_token)
                try:
                    raw = lines.get(timeout=min(remaining, 10))
                except queue.Empty:
                    yield None  # heartbeat; loop re-checks the deadline
                    continue
                if raw is None:
                    detail = "; ".join(stderr_tail[-3:]) or "no details"
                    raise AgentError("agent_crashed", f"The agent process ended unexpectedly ({detail}).",
                                     retryable=True, partial=got_token)
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                kind = rec.get("type")
                if kind == "response" and rec.get("success") is False:
                    raise AgentError("agent_rejected", str(rec.get("error", "request rejected")))
                if kind == "message_update":
                    ev = rec.get("assistantMessageEvent", {})
                    if ev.get("type") == "text_delta" and ev.get("delta"):
                        got_token = True
                        yield ev["delta"]
                elif kind == "message_end":
                    msg = rec.get("message", {})
                    if msg.get("role") == "assistant" and msg.get("stopReason") == "error":
                        last_error = msg.get("errorMessage") or "unknown model error"
                elif kind == "auto_retry_start":
                    log.warning("agent retry", extra={"attempt": rec.get("attempt"), "error": rec.get("errorMessage")})
                elif kind == "auto_retry_end" and rec.get("success") is False:
                    last_error = rec.get("finalError") or last_error
                elif kind == "agent_settled":
                    if last_error and not got_token:
                        raise AgentError("model_error", _friendly(provider, last_error), retryable=True)
                    if last_error and got_token and rec.get("aborted"):
                        raise AgentError("model_error", _friendly(provider, last_error), partial=True)
                    return
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()


def _friendly(provider: str, err: str) -> str:
    e = err.lower()
    if provider == "ollama" and ("connection" in e or "refused" in e or "fetch failed" in e):
        return ("Cannot reach Ollama. Open the Ollama app (or run `ollama serve`) and check "
                f"`ollama list` shows {settings.ollama_chat_model}.")
    if "not found" in e and provider == "ollama":
        return f"Ollama does not have the model {settings.ollama_chat_model}. Run: ollama pull {settings.ollama_chat_model}"
    if provider == "anthropic" and ("401" in e or "auth" in e or "api key" in e):
        return "The Anthropic API key was rejected. Check ANTHROPIC_API_KEY."
    return f"The {provider} model returned an error: {err}"


def get_agent() -> PiAgent:
    return PiAgent()
