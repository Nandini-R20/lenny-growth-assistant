"""Terminal test:  python -m app.search "How do I find product-market fit?" """
import sys

from .retrieval import search

if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "How do you find product-market fit?"
    hits = search(q)
    if not hits:
        print("No relevant transcript material found (this is the 'I don't know' path).")
    for i, h in enumerate(hits, 1):
        print(f"\n[{i}] {h.guest} - {h.title}  (similarity {h.similarity:.2f})")
        print(f"    {h.link}")
        print("    " + h.content[:300].replace("\n", " ") + "...")
