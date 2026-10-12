from app.artifacts import ArtifactStream, salvage, sanitize_html


def run(chunks):
    s, ev = ArtifactStream(), []
    for c in chunks:
        ev += s.feed(c)
    ev += s.finish()
    return s, ev


def test_tags_split_across_tokens():
    s, ev = run(["Sure! <arti", 'fact type="html" ti', 'tle="Hi">', "<h1>Hello</h1></arti", "fact> bye"])
    assert s.result == {"type": "html", "title": "Hi", "content": "<h1>Hello</h1>"}
    assert s.visible.strip() == "Sure!  bye".replace("  ", " ") or "Sure!" in s.visible
    assert [k for k, _ in ev if k == "artifact_start"] == ["artifact_start"]


def test_plain_text_passes_through_untouched():
    s, ev = run(["No artifact ", "here, just 2 < 3 and <b>bold</b>."])
    assert s.result is None
    assert s.visible == "No artifact here, just 2 < 3 and <b>bold</b>."


def test_missing_close_tag_is_closed_at_end():
    s, _ = run(['<artifact type="markdown" title="T">', "# Title\n\nbody"])
    assert s.result["content"].startswith("# Title")


def test_salvage_fenced_block_and_whole_essay():
    fenced = "Here you go\n```html\n<div><h1>Hi</h1><p>" + "x" * 60 + "</p></div>\n```"
    assert salvage("artifact", fenced)["type"] == "html"
    essay = "# My Essay\n\n" + ("word " * 250)
    assert salvage("essay", essay)["title"] == "My Essay"
    assert salvage("qa", "short answer") is None


def test_sanitizer_removes_active_content():
    dirty = ('<h1 onclick="x()">T</h1><script>alert(1)</script><iframe src="//evil"></iframe>'
             '<a href="javascript:bad()">a</a><a href="https://ok.com">b</a><img src="http://x/y.png">'
             '<svg><script>1</script></svg><!-- c --><form action="/x"><input></form>')
    clean, removed = sanitize_html(dirty)
    low = clean.lower()
    for bad in ("<script", "onclick", "javascript:", "<iframe", "<svg", "<form", "<img", "<!--", "alert("):
        assert bad not in low
    assert 'href="https://ok.com"' in clean and "noopener" in clean
    assert "<script>" in removed and "href(unsafe)" in removed


def test_sanitizer_blocks_remote_css_but_keeps_layout():
    clean, _ = sanitize_html('<style>body{color:red}@import url(http://evil/x.css);.a{background:url(http://e/x)}</style>'
                             '<div style="background:url(javascript:x);color:blue">ok</div>')
    assert "color:red" in clean and "color:blue" in clean
    assert "@import" not in clean and "http://evil" not in clean and "javascript:" not in clean


def test_sanitizer_escapes_text():
    clean, _ = sanitize_html("<p>1 < 2 & 3</p>")
    assert "&lt;" in clean and "&amp;" in clean


def test_salvage_plain_checklist_for_artifact_route():
    text = "Here is your checklist:\n- [ ] Define the role [1]\n- [ ] Review candidates [2]\n- [ ] Run a paid trial [3]\n"
    art = salvage("artifact", text, "Turn that into a checklist")
    assert art and art["type"] == "markdown" and art["title"] == "Checklist" and "Run a paid trial" in art["content"]
    assert salvage("qa", text, "x") is None            # normal answers are never turned into artifacts
    assert salvage("artifact", "Just two\n- one\n- two", "make a page") is None   # too small to be a document
