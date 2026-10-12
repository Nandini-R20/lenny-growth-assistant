"""Terminal client for the running API (handy before the UI exists, and for demos/debugging).

  python -m app.chat_cli "How do you hire a head of growth?"
  python -m app.chat_cli "Write an essay on hiring a head of growth"
  python -m app.chat_cli --provider anthropic "What is product-market fit?"
"""
import argparse
import json
import sys

import httpx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("message")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--provider", choices=["ollama", "anthropic"])
    ap.add_argument("--session", help="reuse a session id for follow-up questions")
    args = ap.parse_args()

    sid = args.session or httpx.post(f"{args.base}/api/sessions", timeout=10).json()["id"]
    body = {"content": args.message, **({"provider": args.provider} if args.provider else {})}
    sources, name = [], None
    with httpx.stream("POST", f"{args.base}/api/sessions/{sid}/messages", json=body, timeout=None) as r:
        if r.status_code != 200:
            r.read()
            print("ERROR:", json.dumps(r.json(), indent=2))
            sys.exit(1)
        for line in r.iter_lines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                d = json.loads(line[5:])
                if name == "meta":
                    sources = d["sources"]
                    print(f"[{d['route']} via {d['provider']} / {d['model']}]  sources: {len(sources)}", flush=True)
                elif name == "status" and d.get("elapsed_s"):
                    print(f"  ...still working ({d['elapsed_s']}s)", flush=True)
                elif name == "token":
                    print(d["text"], end="", flush=True)
                elif name == "artifact_end":
                    print(f"\n[artifact: {d['type']} '{d['title']}', {len(d['content'].split())} words]", flush=True)
                elif name == "fallback":
                    print(f"\n[cloud failed, using local model: {d['reason']}]", flush=True)
                elif name == "error":
                    print(f"\nERROR {d['code']}: {d['message']}")
                elif name == "done":
                    g = d.get("grounding", {})
                    print(f"\n\n[done in {d.get('latency_ms', 0) / 1000:.1f}s | cited: {g.get('cited')}]")
    for s in sources:
        print(f"  [{s['n']}] {s['guest']} - {s['episode'][:60]}  {s['url']}")
    print(f"\nsession: {sid}  (use --session {sid} for a follow-up)")


if __name__ == "__main__":
    main()
