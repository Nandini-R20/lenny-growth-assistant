from app.eval import run_cases
from tests.conftest import make_hit


def test_eval_scores_hits_rank_and_rejections():
    cases = [{"q": "a", "expect": ["ep-2"]}, {"q": "b", "expect": ["zzz"]}, {"q": "c", "none": True}, {"q": "d", "none": True}]

    def fake_search(q, k):
        return {"a": [make_hit(1), make_hit(2)], "b": [make_hit(1)], "c": [], "d": [make_hit(3, 0.71)]}[q]

    r = run_cases(cases, fake_search, 6)
    assert r["pos_total"] == 2 and r["hit_at_k"] == 0.5 and r["mrr"] == 0.25
    assert r["neg_total"] == 2 and r["neg_correct"] == 0.5
