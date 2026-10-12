"""Builds the user message the agent sees: retrieved sources + short history + the request.
The static rules live in pi_agent/SYSTEM.md; the Ship 30 rules live in the skill."""
from .config import settings

MAX_HISTORY_CHARS = 700


def format_sources(hits) -> str:
    parts = []
    for i, h in enumerate(hits, 1):
        limit = settings.max_source_chars
        text = h.content if len(h.content) <= limit else h.content[:limit] + " ..."
        parts.append(f'<source id="{i}" guest="{h.guest}" episode="{h.title}" at="{h.start_ts or "n/a"}">\n{text}\n</source>')
    return "<sources>\n" + "\n".join(parts) + "\n</sources>"


def format_history(history: list[dict]) -> str:
    turns = history[-(settings.history_turns * 2):]
    lines = []
    for m in turns:
        who = "User" if m["role"] == "user" else "Assistant"
        content = m["content"]
        if m["role"] == "assistant" and m.get("artifact"):
            content = f'{content} [created an artifact titled "{m["artifact"].get("title", "")}"]'
        if len(content) > MAX_HISTORY_CHARS:
            content = content[:MAX_HISTORY_CHARS] + " ..."
        lines.append(f"{who}: {content}")
    return "\n".join(lines)


import re

QA_HINT = "Answer the question in under 250 words, with [n] citations, using only the sources above."


def artifact_hint(request: str) -> str:
    """Tell the model exactly which artifact to write. The type follows what the user asked for."""
    r = request.lower()
    is_html = bool(re.search(r"\bhtml\b|web ?page|landing page|\bpage\b|one[- ]?pager", r))
    kind = "html" if is_html else "markdown"
    rules = ("Create the requested document from the conversation and the sources above. "
             "Write every item in your own words; never copy or paste excerpt text. "
             "Each item is one actionable line of at most 20 words ending with a [n] citation. "
             "Do not add a list of sources or quotes. ")
    if kind == "html":
        fmt = ('Return it as one block: <artifact type="html" title="Short title"> ... </artifact> containing a clean '
               "HTML fragment with a heading and a list (<h1>, <ul>, <li>) and inline CSS only, no scripts. ")
        if "checklist" in r:
            fmt += "Start each <li> with the symbol \u2610. "
    else:
        fmt = ('Return it as one block: <artifact type="markdown" title="Short title"> ... </artifact> in Markdown. ')
        if "checklist" in r:
            fmt += "Use task items like '- [ ] Do this [1]' under a short heading. "
    return rules + fmt + "Do not write the document outside the block."


def hint_for(route: str, request: str) -> str:
    return {"qa": QA_HINT, "artifact": artifact_hint(request), "essay": ESSAY_HINT}[route]


def build_message(route: str, request: str, hits, history: list[dict]) -> str:
    body = f"{format_sources(hits)}\n\n"
    if history:
        body += f"Conversation so far:\n{format_history(history)}\n\n"
    body += f"Request: {request}\n"
    hint = hint_for(route, request)
    if hint:
        body += f"\n{hint}\n"
    if route == "essay":
        # /skill:<name> makes Pi load the skill instructions into this prompt
        return "/skill:ship30-essay " + body
    return body


ESSAY_HINT = ("Length is a hard requirement: write 1,200 to 1,400 words, never fewer than 1,100. "
              "Structure: a 2-3 sentence hook, a short intro, then exactly 6 headed sections of about 170 words each "
              "(each with a transcript quote or example and a [n] citation), then a 100-word takeaway. "
              "Do not stop early and do not summarize. Expand each section with the examples and reasoning from the excerpts.")
