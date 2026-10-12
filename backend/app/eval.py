"""Retrieval evaluation: does the right episode come back, and do off-topic questions return nothing?

  python -m app.eval            # prints a table and the summary
  python -m app.eval --write    # also writes docs/eval-results.md (include it in your submission)

Metrics: hit@k (an expected episode is in the results), MRR (how early it appears), and the share of
off-topic questions correctly rejected by the similarity threshold. Requires the index and Ollama (query embeddings).
"""
import argparse
import json
from datetime import date
from pathlib import Path

from .config import BACKEND_DIR, settings


def run_cases(cases: list[dict], search_fn, k: int) -> dict:
    rows, hits, rr, neg_total, neg_ok, pos_total = [], 0, 0.0, 0, 0, 0
    for c in cases:
        res = search_fn(c["q"], k=k)
        slugs = [h.slug for h in res]
        if c.get("none"):
            neg_total += 1
            ok = not res
            neg_ok += ok
            rows.append({"q": c["q"], "kind": "off-topic", "ok": ok, "top": slugs[:1] or ["(none)"],
                         "sim": round(res[0].similarity, 2) if res else None, "rank": None})
            continue
        pos_total += 1
        rank = next((i for i, s in enumerate(slugs, 1) if s in c["expect"]), None)
        hits += rank is not None
        rr += 1 / rank if rank else 0
        rows.append({"q": c["q"], "kind": "on-topic", "ok": rank is not None, "top": slugs[:3],
                     "sim": round(res[0].similarity, 2) if res else None, "rank": rank})
    return {"rows": rows, "k": k, "pos_total": pos_total, "hit_at_k": hits / pos_total if pos_total else 0,
            "mrr": rr / pos_total if pos_total else 0, "neg_total": neg_total,
            "neg_correct": neg_ok / neg_total if neg_total else 1}


def to_markdown(r: dict, model: str) -> str:
    out = [f"# Retrieval evaluation ({date.today()})", "",
           f"Embedding model `{model}`, top-k = {r['k']}, threshold `MIN_SIMILARITY={settings.min_similarity}`.", "",
           f"- **hit@{r['k']}**: {r['hit_at_k']:.0%} of {r['pos_total']} on-topic questions return an expected episode",
           f"- **MRR**: {r['mrr']:.2f}",
           f"- **Off-topic rejected**: {r['neg_correct']:.0%} of {r['neg_total']}", "",
           "| Question | Type | Result | Rank | Top similarity | Top episodes |", "|---|---|---|---|---|---|"]
    for x in r["rows"]:
        out.append(f"| {x['q']} | {x['kind']} | {'pass' if x['ok'] else 'FAIL'} | {x['rank'] or '-'} | {x['sim'] if x['sim'] is not None else '-'} | {', '.join(x['top'])} |")
    out += ["", "Cases live in `backend/eval/retrieval_cases.json`; failures are listed, not hidden. "
            "A miss can mean the episode is not in the indexed sample, not only a retrieval error."]
    return "\n".join(out) + "\n"


def main() -> None:
    from .retrieval import search
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--k", type=int, default=6)
    a = ap.parse_args()
    cases = json.loads((BACKEND_DIR / "eval" / "retrieval_cases.json").read_text(encoding="utf-8"))["cases"]
    r = run_cases(cases, lambda q, k: search(q, k=k), a.k)
    md = to_markdown(r, settings.embed_model)
    print(md)
    if a.write:
        p = BACKEND_DIR.parent / "docs" / "eval-results.md"
        p.write_text(md, encoding="utf-8")
        print("wrote", p)


if __name__ == "__main__":
    main()
