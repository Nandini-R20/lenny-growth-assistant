"""FastAPI application: sessions, grounded chat (SSE streaming), health, config.

Request flow for POST /api/sessions/{id}/messages:
  validate -> persist user msg -> route (qa | essay | artifact) -> retrieve from pgvector
  -> (no support? answer deterministically, no model call) -> Pi agent (Ollama or Claude)
  -> stream tokens + artifact events -> persist assistant msg with sources + artifact.
"""
import json
import logging
import re
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal, Optional

import httpx
import pg8000.exceptions
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import store
from .agent import AgentError, get_agent, model_for, pi_path, provider_status
from .artifacts import ArtifactStream, salvage, sanitize_html
from .config import BACKEND_DIR, settings
from .db import connect, init_schema, run
from .embeddings import EmbeddingError
from .logging_setup import setup as setup_logging
from .prompts import build_message
from .retrieval import hits_by_ids, search
from .router import classify, needs_context
from .seed import seed_if_empty

setup_logging(settings.log_level)
log = logging.getLogger("api")

NO_SUPPORT = ("The Lenny's Podcast transcripts I have indexed don't cover that well enough for me to answer "
              "without guessing. Try a question about product, growth, hiring, strategy or leadership, "
              "or ask me to build on something we already discussed.")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details


def error_body(code: str, message: str, details=None, request_id: str | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details, "request_id": request_id}}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_schema()
    except Exception as e:  # app still starts; /health/ready reports the problem
        log.error("database init failed", extra={"error": str(e)})
    else:
        threading.Thread(target=seed_if_empty, daemon=True).start()  # first run: load the bundled index
    yield


app = FastAPI(title="The Lenny Growth Assistant", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.rid = rid
    t0 = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    log.info("request", extra={"rid": rid, "method": request.method, "path": request.url.path,
                               "status": response.status_code, "ms": int((time.monotonic() - t0) * 1000)})
    return response


def _rid(request: Request) -> str | None:
    return getattr(request.state, "rid", None)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(error_body(exc.code, exc.message, exc.details, _rid(request)), status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    details = [{"field": ".".join(str(x) for x in e["loc"][1:]), "problem": e["msg"]} for e in exc.errors()]
    return JSONResponse(error_body("validation_error", "The request is not valid.", details, _rid(request)), status_code=422)


@app.exception_handler(pg8000.exceptions.InterfaceError)
@app.exception_handler(ConnectionError)
async def db_down_handler(request: Request, exc: Exception):
    log.error("database unavailable", extra={"error": str(exc), "rid": _rid(request)})
    return JSONResponse(error_body("database_unavailable",
                        "The database is not reachable. Start it with: docker compose up -d", None, _rid(request)),
                        status_code=503)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error", extra={"rid": _rid(request)})
    return JSONResponse(error_body("internal_error", "Something went wrong on the server.", None, _rid(request)),
                        status_code=500)


# ------------------------------------------------------------------ schemas
class SessionCreate(BaseModel):
    client_id: Optional[str] = None


class MessageIn(BaseModel):
    content: str
    provider: Optional[Literal["ollama", "anthropic"]] = None


# ------------------------------------------------------------------ health + config
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    checks: dict = {}
    try:
        checks["database"] = {"ok": True, **store.index_stats()}
    except Exception as e:
        checks["database"] = {"ok": False, "error": str(e)[:200]}
    checks["agent_cli"] = {"ok": bool(pi_path())}
    try:
        r = httpx.get(settings.ollama_base_url.rstrip("/") + "/api/tags", timeout=2)
        names = [m.get("name") for m in r.json().get("models", [])]
        checks["ollama"] = {"ok": True, "chat_model_pulled": settings.ollama_chat_model in names,
                            "embed_model_pulled": any(n and n.startswith(settings.embed_model) for n in names)}
    except Exception:
        checks["ollama"] = {"ok": False, "error": "unreachable"}
    checks["anthropic_key"] = {"ok": bool(settings.anthropic_api_key)}
    critical = checks["database"]["ok"] and checks["agent_cli"]["ok"]
    return JSONResponse({"status": "ok" if critical and checks["ollama"]["ok"] else "degraded", "checks": checks},
                        status_code=200 if critical else 503)


@app.get("/api/config")
def config():
    try:
        index = store.index_stats()
    except Exception:
        index = None
    return {"default_provider": settings.default_provider, "providers": provider_status(),
            "fallback_to_local": settings.fallback_to_local, "index": index,
            "limits": {"max_message_chars": settings.max_message_chars}}


# ------------------------------------------------------------------ sessions
@app.post("/api/sessions", status_code=201)
def create_session(request: Request, body: SessionCreate | None = None):
    meta = {"client_id": body.client_id if body else None,
            "user_agent": request.headers.get("user-agent", "")[:200],
            "ip": request.client.host if request.client else None}
    return store.create_session(meta)


@app.get("/api/sessions")
def list_sessions(limit: int = 50):
    return {"sessions": store.list_sessions(max(1, min(limit, 200)))}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    s = store.get_session(session_id)
    if not s:
        raise ApiError(404, "session_not_found", "That chat does not exist.")
    return s


@app.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(session_id: str):
    if not store.delete_session(session_id):
        raise ApiError(404, "session_not_found", "That chat does not exist.")
    return Response(status_code=204)


# ------------------------------------------------------------------ chat turn
def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def source_card(n: int, h) -> dict:
    return {"n": n, "chunk_id": h.chunk_id, "guest": h.guest, "episode": h.title, "url": h.link,
            "at": h.start_ts, "similarity": round(h.similarity, 3),
            "quote": " ".join(h.content.split())[:240]}


CITE_RE = re.compile(r"\[(\d+)\]")


def gather_sources(route: str, content: str, hist: list[dict]):
    """Retrieve for this turn. Follow-ups reuse what the previous answer was built on."""
    k, per_ep = {"qa": (settings.top_k, 2), "artifact": (8, 2), "essay": (10, 3)}[route]
    query = content
    prev_ids: list[int] = []
    if hist and needs_context(content):
        prev_user = next((m["content"] for m in reversed(hist) if m["role"] == "user"), "")
        query = f"{prev_user} {content}".strip()
        prev_assistant = next((m for m in reversed(hist) if m["role"] == "assistant"), None)
        if prev_assistant:
            prev_ids = [s["chunk_id"] for s in prev_assistant["sources"] if "chunk_id" in s]
    hits = hits_by_ids(prev_ids) if prev_ids and route != "qa" else []
    seen = {h.chunk_id for h in hits}
    for h in search(clean_query(query, route), k=k, per_episode=per_ep):
        if h.chunk_id not in seen:
            hits.append(h)
            seen.add(h.chunk_id)
    return hits[:k], query


def safe_turn(session_id: str, content: str, provider: str, hist: list[dict]):
    """Never let an unexpected bug leave the browser with a silent, empty stream."""
    try:
        yield from run_turn(session_id, content, provider, hist)
    except GeneratorExit:
        raise
    except Exception:
        log.exception("turn crashed", extra={"session": session_id})
        yield sse("error", {"code": "internal_error", "message": "Something went wrong while answering. Please try again.", "partial": False})


def run_turn(session_id: str, content: str, provider: str, hist: list[dict]):
    t0 = time.monotonic()
    route = classify(content)
    log.info("turn start", extra={"session": session_id, "route": route, "provider": provider})
    yield sse("status", {"phase": "searching"})
    try:
        hits, query = gather_sources(route, content, hist)
    except EmbeddingError as e:
        log.error("embedding failed", extra={"error": str(e)})
        yield sse("error", {"code": "embedding_unavailable", "message": str(e), "partial": False})
        return
    except (pg8000.exceptions.InterfaceError, ConnectionError):
        yield sse("error", {"code": "database_unavailable",
                            "message": "The database is not reachable. Start it with: docker compose up -d",
                            "partial": False})
        return
    top = round(hits[0].similarity, 3) if hits else None
    log.info("retrieval", extra={"session": session_id, "route": route, "hits": len(hits), "top_similarity": top})

    sources = [source_card(i, h) for i, h in enumerate(hits, 1)]
    if not hits:  # grounded-or-silent: never call the model without evidence
        mid = store.add_message(session_id, "assistant", NO_SUPPORT, route=route, provider="none",
                                latency_ms=int((time.monotonic() - t0) * 1000))
        yield sse("meta", {"route": route, "provider": "none", "model": None, "sources": []})
        yield sse("token", {"text": NO_SUPPORT})
        yield sse("done", {"message_id": mid, "route": route, "grounding": {"supported": False}})
        return

    message = build_message(route, content, hits, hist)
    active, fallback_used, text, stream = provider, False, "", None
    t_gen, ttft_ms = time.monotonic(), None
    while True:
        model = model_for(active)
        yield sse("meta", {"route": route, "provider": active, "model": model, "sources": sources,
                           "fallback": fallback_used})
        yield sse("status", {"phase": "thinking"})
        stream, text = ArtifactStream(), ""
        try:
            for delta in get_agent().stream(active, message):
                if delta is None:
                    yield ": keep-alive\n\n"
                    yield sse("status", {"phase": "thinking", "elapsed_s": int(time.monotonic() - t0)})
                    continue
                if ttft_ms is None:
                    ttft_ms = int((time.monotonic() - t_gen) * 1000)
                text += delta
                for kind, payload in stream.feed(delta):
                    yield from _emit(kind, payload)
            break
        except AgentError as e:
            log.error("agent error", extra={"code": e.code, "provider": active, "partial": e.partial,
                                            "session": session_id})
            if (active == "anthropic" and settings.fallback_to_local and not e.partial):
                active, fallback_used = "ollama", True
                yield sse("fallback", {"from": "anthropic", "to": "ollama", "reason": e.message})
                continue
            if e.partial and text.strip():
                for kind, payload in stream.finish():
                    yield from _emit(kind, payload)
                visible = (stream.visible or "").strip()
                if visible:
                    store.add_message(session_id, "assistant", visible + "\n\n_(response interrupted)_",
                                      route=route, provider=active, model=model, sources=sources)
            yield sse("error", {"code": e.code, "message": e.message, "partial": e.partial})
            return
        except GeneratorExit:  # client disconnected: Pi process is killed in agent.stream's finally
            log.info("client disconnected", extra={"session": session_id})
            raise

    for kind, payload in stream.finish():
        yield from _emit(kind, payload)
    if text.strip().upper().startswith("NO_ANSWER"):  # the model judged the excerpts irrelevant
        latency = int((time.monotonic() - t0) * 1000)
        log.info("model declined", extra={"session": session_id, "route": route, "ms": latency})
        yield sse("replace_text", {"text": NO_SUPPORT})
        mid = store.add_message(session_id, "assistant", NO_SUPPORT, route=route, provider="none", latency_ms=latency)
        yield sse("done", {"message_id": mid, "route": route, "provider": "none", "model": None, "latency_ms": latency,
                           "ttft_ms": ttft_ms, "grounding": {"supported": False}, "fallback": fallback_used})
        return
    artifact = stream.result
    visible = (stream.visible or "").strip()
    if artifact is None and route in ("artifact", "essay"):
        artifact = salvage(route, text, content)
        if artifact:
            log.warning("artifact salvaged", extra={"route": route})
            yield sse("artifact_start", {"type": artifact["type"], "title": artifact["title"]})
            if artifact["content"] == text.strip():  # whole reply was the essay: don't duplicate it in chat
                visible = f'I created "{artifact["title"]}". It is open in the viewer.'
                yield sse("replace_text", {"text": visible})
            yield from _emit("artifact_end", artifact)
    if artifact and artifact["type"] == "html":
        clean, removed = sanitize_html(artifact["content"])
        artifact = {**artifact, "content": clean, "sanitized": True, "removed": removed}
        if removed:
            log.warning("html sanitized", extra={"removed": removed, "session": session_id})
    if artifact and not visible:
        visible = f'Created "{artifact["title"]}" in the viewer.'

    cited = sorted({int(n) for n in CITE_RE.findall(text) if 1 <= int(n) <= len(hits)})
    grounding = {"supported": True, "cited": cited, "uncited": route == "qa" and not cited}
    if grounding["uncited"]:
        log.warning("answer without citations", extra={"session": session_id})
    latency = int((time.monotonic() - t0) * 1000)
    mid = store.add_message(session_id, "assistant", visible or text.strip(), route=route, provider=active,
                            model=model_for(active), sources=sources, artifact=artifact, latency_ms=latency)
    log.info("turn done", extra={"session": session_id, "route": route, "provider": active, "ms": latency,
                                 "cited": len(cited), "artifact": bool(artifact), "fallback": fallback_used,
                                 "ttft_ms": ttft_ms, "prompt_chars": len(message)})
    yield sse("done", {"message_id": mid, "route": route, "provider": active, "model": model_for(active),
                       "latency_ms": latency, "ttft_ms": ttft_ms, "grounding": grounding, "fallback": fallback_used,
                       "artifact": artifact})


def _emit(kind: str, payload):
    if kind == "text":
        yield sse("token", {"text": payload})
    elif kind == "artifact_start":
        yield sse("artifact_start", payload)
    elif kind == "artifact_delta":
        yield sse("artifact_delta", {"text": payload})
    elif kind == "artifact_end":
        art = payload
        if art["type"] == "html":
            clean, removed = sanitize_html(art["content"])
            art = {**art, "content": clean, "sanitized": True, "removed": removed}
        yield sse("artifact_end", art)


@app.post("/api/sessions/{session_id}/messages")
def post_message(session_id: str, body: MessageIn):
    content = body.content.strip()
    if not content:
        raise ApiError(422, "validation_error", "Message is empty.", [{"field": "content", "problem": "must not be blank"}])
    if len(content) > settings.max_message_chars:
        raise ApiError(422, "message_too_long", f"Messages can be up to {settings.max_message_chars} characters.")
    if not store.get_session(session_id):
        raise ApiError(404, "session_not_found", "That chat does not exist. Start a new chat.")
    provider = body.provider or settings.default_provider
    status = {p["id"]: p for p in provider_status()}.get(provider)
    if not status or not status["available"]:
        raise ApiError(409, "provider_unavailable",
                       status["reason"] if status else f"Unknown provider {provider}.",
                       {"available": [p["id"] for p in provider_status() if p["available"]]})
    hist = store.history(session_id)
    store.add_message(session_id, "user", content)
    return StreamingResponse(safe_turn(session_id, content, provider, hist), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ web UI (no build step)
# Must stay LAST so it never shadows /api or /health routes.
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="ui")


def clean_query(q: str, route: str) -> str:
    """For essay requests, search on the topic only: 'Ship 30 for 30 essay' words skew the embedding."""
    if route != "essay":
        return q
    q = re.sub(r"(?i)ship\s?-?30(\s+for\s+30)?|\b(write|draft|create|generate)\b|\b(an?|the)\b|\b(atomic\s+)?(essay|newsletter|blog\s?post|article)\b", " ", q)
    return " ".join(q.split()) or q
