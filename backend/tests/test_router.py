import pytest

from app.router import classify, needs_context


@pytest.mark.parametrize("msg,route", [
    ("What is product-market fit?", "qa"),
    ("How do you hire a head of growth?", "qa"),
    ("What is a PRD document?", "qa"),
    ("Write an essay on retention", "essay"),
    ("Draft a Ship 30 post about onboarding", "essay"),
    ("Can you write me a newsletter about pricing?", "essay"),
    ("Make an HTML checklist for hiring", "artifact"),
    ("turn that into a one-pager", "artifact"),
    ("Create a table comparing PLG and sales-led", "artifact"),
    ("Summarize what Todd Jackson said", "qa"),
])
def test_classify(msg, route):
    assert classify(msg) == route


def test_followups_need_context():
    assert needs_context("turn that into a checklist")
    assert needs_context("why?")
    assert not needs_context("What does Todd Jackson recommend for measuring product-market fit in B2B startups?")
