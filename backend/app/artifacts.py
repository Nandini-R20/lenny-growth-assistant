"""Artifact handling: stream parser, fallbacks, and HTML sanitizer.

The model wraps documents in  <artifact type="markdown|html" title="..."> ... </artifact>.
ArtifactStream splits a token stream into visible chat text and artifact content, even when the
tags arrive split across tokens. Small local models sometimes forget the tags, so `salvage`
recovers a fenced code block (or the whole essay) instead of losing the work.

Security: generated HTML is untrusted. `sanitize_html` is defence in depth (allow-list, drops
scripts/handlers/remote resources). The viewer additionally renders inside a sandboxed iframe
with no script permission and a strict CSP (see docs/architecture.md).
"""
import html
import re
from html.parser import HTMLParser

OPEN_RE = re.compile(r"<artifact\b([^>]*)>", re.I)
CLOSE_TAG = "</artifact>"
ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"|(\w+)\s*=\s*\'([^\']*)\'')
MAX_ARTIFACT_CHARS = 120_000


def _attrs(raw: str) -> dict:
    out = {}
    for m in ATTR_RE.finditer(raw):
        out[(m.group(1) or m.group(3)).lower()] = m.group(2) if m.group(1) else m.group(4)
    return out


def _held_back(buf: str, token: str) -> int:
    """Length of a suffix of buf that could be the start of `token` (case-insensitive)."""
    low = buf.lower()
    for n in range(min(len(token) - 1, len(buf)), 0, -1):
        if token.startswith(low[-n:]):
            return n
    return 0


class ArtifactStream:
    """Feed text deltas; get back a list of events: (kind, payload).
    kinds: 'text' (visible chat), 'artifact_start' ({type,title}), 'artifact_delta' (str), 'artifact_end'."""

    def __init__(self) -> None:
        self.buf = ""
        self.inside = False
        self.type = "markdown"
        self.title = "Untitled"
        self.content = ""
        self.done = False  # an artifact was completed
        self.result: dict | None = None
        self.visible = ""

    def feed(self, delta: str) -> list[tuple[str, object]]:
        self.buf += delta
        return self._drain(final=False)

    def finish(self) -> list[tuple[str, object]]:
        ev = self._drain(final=True)
        if self.inside:  # model forgot the closing tag: close it ourselves
            ev += self._close()
        return ev

    def _close(self) -> list[tuple[str, object]]:
        self.inside = False
        self.done = True
        self.result = {"type": self.type, "title": self.title, "content": self.content.strip()}
        return [("artifact_end", self.result)]

    def _drain(self, final: bool) -> list[tuple[str, object]]:
        events: list[tuple[str, object]] = []
        while True:
            if not self.inside:
                m = OPEN_RE.search(self.buf)
                if m:
                    before = self.buf[: m.start()]
                    if before:
                        self.visible += before
                        events.append(("text", before))
                    a = _attrs(m.group(1))
                    self.type = "html" if a.get("type", "").lower() == "html" else "markdown"
                    self.title = (a.get("title") or "Untitled")[:120]
                    self.content = ""
                    self.inside = True
                    self.buf = self.buf[m.end():].lstrip("\n")
                    events.append(("artifact_start", {"type": self.type, "title": self.title}))
                    continue
                keep = 0 if final else _held_back(self.buf, "<artifact")
                # also hold back an incomplete opening tag like '<artifact type="ht'
                idx = self.buf.lower().rfind("<artifact")
                if idx != -1 and not final:
                    keep = len(self.buf) - idx
                emit = self.buf[: len(self.buf) - keep] if keep else self.buf
                if emit:
                    self.visible += emit
                    events.append(("text", emit))
                self.buf = self.buf[len(self.buf) - keep:] if keep else ""
                break
            else:
                idx = self.buf.lower().find(CLOSE_TAG)
                if idx != -1:
                    chunk = self.buf[:idx]
                    if chunk:
                        self.content += chunk
                        events.append(("artifact_delta", chunk))
                    self.buf = self.buf[idx + len(CLOSE_TAG):]
                    events += self._close()
                    continue
                keep = 0 if final else _held_back(self.buf, CLOSE_TAG)
                emit = self.buf[: len(self.buf) - keep] if keep else self.buf
                if emit:
                    self.content += emit
                    events.append(("artifact_delta", emit))
                self.buf = self.buf[len(self.buf) - keep:] if keep else ""
                if len(self.content) > MAX_ARTIFACT_CHARS:
                    events += self._close()
                break
        return events


FENCE_RE = re.compile(r"```(html|markdown|md)?\s*\n(.*?)```", re.S | re.I)


LIST_LINE = re.compile(r"^\s*([-*+]|\d+[.)]|#{1,4})\s+\S", re.M)


def salvage(route: str, full_text: str, request: str = "") -> dict | None:
    """Recover an artifact when the model skipped the <artifact> tags."""
    m = FENCE_RE.search(full_text)
    if m and len(m.group(2).strip()) > 40:
        kind = "html" if (m.group(1) or "").lower() == "html" or "<html" in m.group(2).lower() \
            or "<div" in m.group(2).lower() else "markdown"
        first = re.search(r"^#\s+(.+)$", m.group(2), re.M)
        return {"type": kind, "title": (first.group(1) if first else "Untitled")[:120],
                "content": m.group(2).strip()}
    if route == "artifact" and len(LIST_LINE.findall(full_text)) >= 3:
        # the model wrote a list/document in plain chat text without the artifact tags
        first = re.search(r"^#{1,3}\s+(.+)$", full_text, re.M)
        words = re.sub(r"[^\w\s-]", "", request).split()
        guess = "Checklist" if "checklist" in request.lower() else ("Outline" if "outline" in request.lower() else "Document")
        title = (first.group(1) if first else guess)[:120]
        return {"type": "markdown", "title": title, "content": full_text.strip()}
    if route == "essay" and len(full_text.split()) > 200:
        first = re.search(r"^#{1,2}\s+(.+)$", full_text, re.M)
        return {"type": "markdown", "title": (first.group(1) if first else "Essay")[:120],
                "content": full_text.strip()}
    return None


# ------------------------------------------------------------------ HTML sanitizer
ALLOWED_TAGS = {
    "html", "body", "div", "span", "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "dl", "dt", "dd", "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "caption", "colgroup", "col", "strong", "b", "em", "i", "u", "s", "small", "mark", "sub", "sup",
    "code", "pre", "kbd", "blockquote", "q", "cite", "a", "section", "article", "header", "footer",
    "nav", "main", "aside", "figure", "figcaption", "details", "summary", "abbr", "time", "style",
    "head", "title",
}
DROP_WITH_CONTENT = {"script", "iframe", "object", "embed", "noscript", "template", "svg", "math",
                     "form", "textarea", "select", "button", "canvas", "audio", "video", "applet"}
VOID = {"br", "hr", "col"}
ALLOWED_ATTRS = {"class", "id", "title", "lang", "dir", "role", "colspan", "rowspan", "scope",
                 "href", "datetime", "open", "style"}
SAFE_HREF = re.compile(r"^(https?:|mailto:|#)", re.I)
# Remove whole constructs, not just keywords: nothing remote may load and nothing may execute.
CSS_RULES = [
    re.compile(r"@import[^;{}]*;?", re.I),
    re.compile(r"url\s*\((?!\s*['\"]?data:image/)[^)]*\)", re.I),
    re.compile(r"expression\s*\([^)]*\)", re.I),
    re.compile(r"(javascript|vbscript):[^;}\"']*", re.I),
    re.compile(r"(behavior|-moz-binding)\s*:[^;}]*", re.I),
]


def sanitize_css(css: str) -> str:
    for rule in CSS_RULES:
        css = rule.sub("/*blocked*/", css)
    return css


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.removed: set[str] = set()
        self.skip_depth = 0
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.skip_depth:
            if tag in DROP_WITH_CONTENT:
                self.skip_depth += 1
            return
        if tag in DROP_WITH_CONTENT:
            self.skip_depth = 1
            self.removed.add(f"<{tag}>")
            return
        if tag not in ALLOWED_TAGS:
            self.removed.add(f"<{tag}>")
            return
        if tag in ("html", "head", "body", "title"):
            return  # the viewer supplies its own document shell
        kept = []
        for name, value in attrs:
            name = name.lower()
            value = value or ""
            if name.startswith("on") or name not in ALLOWED_ATTRS:
                self.removed.add(f"{name}=")
                continue
            if name == "href":
                if not SAFE_HREF.match(value.strip()):
                    self.removed.add("href(unsafe)")
                    continue
            if name == "style":
                value = sanitize_css(value)
            kept.append(f' {name}="{html.escape(value, quote=True)}"')
        if tag == "a":
            kept.append(' rel="noopener noreferrer nofollow" target="_blank"')
        if tag == "style":
            self.in_style = True
        self.out.append(f"<{tag}{''.join(kept)}>")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skip_depth:
            if tag in DROP_WITH_CONTENT:
                self.skip_depth -= 1
            return
        if tag in ALLOWED_TAGS and tag not in VOID and tag not in ("html", "head", "body", "title"):
            if tag == "style":
                self.in_style = False
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self.skip_depth:
            return
        self.out.append(sanitize_css(data) if self.in_style else html.escape(data, quote=False))

    def handle_comment(self, data):  # drop comments (conditional-comment tricks)
        self.removed.add("<!-- -->")


def sanitize_html(src: str) -> tuple[str, list[str]]:
    """Return (clean_html, sorted list of what was removed)."""
    p = _Sanitizer()
    p.feed(src)
    p.close()
    return "".join(p.out).strip(), sorted(p.removed)
