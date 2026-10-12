"""API tests with the agent and retrieval faked (fast, deterministic). Needs the Postgres container;
skipped automatically when the database is not reachable."""
import json

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.agent import AgentError
from app.config import settings
from tests.conftest import FakeAgent, make_hit

try:
    from app.db import connect
    connect().close()
    DB_UP = True
except Exception:
    DB_UP = False

pytestmark = pytest.mark.skipif(not DB_UP, reason="PostgreSQL not reachable (run: docker compose up -d)")


@pytest.fixture
def client(monkeypatch):
    FakeAgent.calls = []
    monkeypatch.setattr(main, "search", lambda q, k=None, per_episode=2: [make_hit(1), make_hit(2)])
    monkeypatch.setattr(main, "hits_by_ids", lambda ids: [make_hit(i) for i in ids])
    with TestClient(main.app) as c:
        yield c


def turn(client, sid, content, provider=None):
    body = {"content": content, **({"provider": provider} if provider else {})}
    events, name = [], None
    with client.stream("POST", f"/api/sessions/{sid}/messages", json=body) as r:
        assert r.status_code == 200, r.text
        for line in r.iter_lines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                events.append((name, json.loads(line[5:])))
    return events


def names(events):
    return [n for n, _ in events]


def new_session(client):
    return client.post("/api/sessions", json={"client_id": "pytest"}).json()["id"]


def test_health_and_config(client):
    assert client.get("/health").json() == {"status": "ok"}
    cfg = client.get("/api/config").json()
    assert {p["id"] for p in cfg["providers"]} == {"ollama", "anthropic"}


def test_grounded_answer_is_cited_and_persisted(client, monkeypatch):
    monkeypatch.setattr(main, "get_agent", lambda: FakeAgent(["Hire after PMF [1]. ", "Look for acquisition experience [2]."]))
    sid = new_session(client)
    ev = turn(client, sid, "How do you hire a head of growth?")
    assert names(ev)[0] == "status" and "done" in names(ev)
    done = dict(ev)["done"]
    assert done["grounding"]["cited"] == [1, 2] and done["route"] == "qa"
    session = client.get(f"/api/sessions/{sid}").json()
    assert session["title"].startswith("How do you hire")
    assistant = session["messages"][-1]
    assert assistant["role"] == "assistant" and len(assistant["sources"]) == 2 and assistant["provider"] == "ollama"


def test_no_support_answers_without_calling_the_model(client, monkeypatch):
    monkeypatch.setattr(main, "search", lambda *a, **k: [])
    monkeypatch.setattr(main, "get_agent", lambda: (_ for _ in ()).throw(AssertionError("model must not be called")))
    sid = new_session(client)
    ev = turn(client, sid, "What is the best pizza topping?")
    assert dict(ev)["done"]["grounding"] == {"supported": False}
    assert "don't cover that" in "".join(d["text"] for n, d in ev if n == "token")


def test_html_artifact_is_sanitized(client, monkeypatch):
    script = ['Here.<artifact type="html" title="Checklist"><h1 onclick="x()">Hi</h1><script>bad()</script></artifact>']
    monkeypatch.setattr(main, "get_agent", lambda: FakeAgent(script))
    sid = new_session(client)
    ev = turn(client, sid, "Make an HTML checklist for hiring")
    art = dict(ev)["done"]["artifact"]
    assert art["sanitized"] and "<script" not in art["content"] and "onclick" not in art["content"]
    stored = client.get(f"/api/sessions/{sid}").json()["messages"][-1]["artifact"]
    assert stored["title"] == "Checklist"


def test_essay_uses_the_skill_and_returns_markdown(client, monkeypatch):
    monkeypatch.setattr(main, "get_agent", lambda: FakeAgent(['Done.<artifact type="markdown" title="Essay"># Essay\n\nBody [1]</artifact>']))
    sid = new_session(client)
    ev = turn(client, sid, "Write an essay on hiring")
    assert dict(ev)["done"]["route"] == "essay" and dict(ev)["done"]["artifact"]["type"] == "markdown"
    assert FakeAgent.calls[-1][1].startswith("/skill:ship30-essay")


def test_followup_gets_history_in_prompt(client, monkeypatch):
    monkeypatch.setattr(main, "get_agent", lambda: FakeAgent())
    sid = new_session(client)
    turn(client, sid, "How do you hire a head of growth?")
    turn(client, sid, "turn that into a checklist")
    assert "User: How do you hire a head of growth?" in FakeAgent.calls[-1][1]


def test_sessions_are_independent(client, monkeypatch):
    monkeypatch.setattr(main, "get_agent", lambda: FakeAgent())
    a, b = new_session(client), new_session(client)
    turn(client, a, "How do you hire a head of growth?")
    assert client.get(f"/api/sessions/{b}").json()["messages"] == []


def test_cloud_failure_falls_back_to_local(client, monkeypatch):
    class Flaky(FakeAgent):
        def stream(self, provider, message):
            if provider == "anthropic":
                raise AgentError("model_error", "boom", retryable=True)
            yield from super().stream(provider, message)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    monkeypatch.setattr(main, "get_agent", lambda: Flaky())
    sid = new_session(client)
    ev = turn(client, sid, "How do you hire a head of growth?", provider="anthropic")
    assert "fallback" in names(ev) and dict(ev)["done"]["provider"] == "ollama" and dict(ev)["done"]["fallback"]


def test_model_failure_without_fallback_is_a_structured_error(client, monkeypatch):
    monkeypatch.setattr(main, "get_agent", lambda: FakeAgent([], AgentError("model_timeout", "too slow", retryable=True)))
    sid = new_session(client)
    ev = turn(client, sid, "How do you hire a head of growth?")
    assert dict(ev)["error"]["code"] == "model_timeout"
    assert [m["role"] for m in client.get(f"/api/sessions/{sid}").json()["messages"]] == ["user"]


def test_validation_and_error_contracts(client):
    sid = new_session(client)
    r = client.post(f"/api/sessions/{sid}/messages", json={"content": "   "})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = client.post(f"/api/sessions/{sid}/messages", json={"content": "x" * (settings.max_message_chars + 1)})
    assert r.status_code == 422 and r.json()["error"]["code"] == "message_too_long"
    r = client.post(f"/api/sessions/{sid}/messages", json={"content": "hi", "provider": "gpt"})
    assert r.status_code == 422
    r = client.post("/api/sessions/does-not-exist/messages", json={"content": "hi"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "session_not_found"
    r = client.post(f"/api/sessions/{sid}/messages", json={"content": "hi", "provider": "anthropic"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "provider_unavailable"
    assert r.headers["x-request-id"]


def test_delete_session(client):
    sid = new_session(client)
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.delete(f"/api/sessions/{sid}").status_code == 404


def test_model_declining_with_sentinel_becomes_the_standard_no_support_message(client, monkeypatch):
    monkeypatch.setattr(main, "get_agent", lambda: FakeAgent(["NO_", "ANSWER"]))
    sid = new_session(client)
    ev = turn(client, sid, "How do you hire a head of growth?")
    d = dict(ev)
    assert d["done"]["grounding"] == {"supported": False} and d["replace_text"]["text"] == main.NO_SUPPORT
    last = client.get(f"/api/sessions/{sid}").json()["messages"][-1]
    assert last["content"] == main.NO_SUPPORT and last["provider"] == "none" and last["sources"] == []


def test_artifact_route_recovers_when_model_forgets_tags(client, monkeypatch):
    plain = ["Here is the checklist:\n", "- [ ] Define the role [1]\n- [ ] Review candidates [2]\n- [ ] Run a trial [1]\n"]
    monkeypatch.setattr(main, "get_agent", lambda: FakeAgent(plain))
    sid = new_session(client)
    ev = turn(client, sid, "Make a checklist for hiring a head of growth")
    d = dict(ev)
    assert "artifact_end" in d and d["done"]["artifact"]["title"] == "Checklist"
    assert client.get(f"/api/sessions/{sid}").json()["messages"][-1]["artifact"]["type"] == "markdown"
