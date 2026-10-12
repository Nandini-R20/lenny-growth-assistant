from app.prompts import build_message
from app.retrieval import is_ad


def test_essay_prompt_forces_skill_and_numbers_sources(hit):
    msg = build_message("essay", "Write an essay on hiring", [hit(1), hit(2)], [])
    assert msg.startswith("/skill:ship30-essay ")
    assert '<source id="1" guest="Guest 1"' in msg and '<source id="2"' in msg


def test_qa_prompt_includes_history_and_artifact_note(hit):
    hist = [{"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1", "artifact": {"title": "My page"}}]
    msg = build_message("qa", "and then?", [hit(1)], hist)
    assert "User: q1" in msg and 'created an artifact titled "My page"' in msg
    assert not msg.startswith("/skill")


def test_ad_filter_needs_two_markers():
    assert is_ad("This episode is brought to you by Acme. Use code LENNY for a free trial.")
    assert not is_ad("We discussed a free trial funnel in depth.")


def test_deep_link_with_and_without_timestamp(hit):
    assert hit(1, ts="01:02:03").link.endswith("&t=3723s")
    assert hit(1, ts="").link == "https://www.youtube.com/watch?v=abc1"


def test_artifact_hint_follows_requested_type(hit):
    html = build_message("artifact", "Make an HTML checklist for hiring", [hit(1)], [])
    md = build_message("artifact", "Turn that into a checklist", [hit(1)], [])
    assert 'type="html"' in html and "\u2610" in html and "never copy" in html
    assert 'type="markdown"' in md and "- [ ] Do this" in md
