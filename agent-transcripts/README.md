# Agent Transcripts

This folder shows how I built the Lenny Growth Assistant with Claude as my AI pair-programmer.

## Files

| File | What it is |
|---|---|
| `SUMMARY.md` | The 20 failures I hit while building, and how each was fixed. Start here. |
| `claude-session-1.md` | Chat 1: secret scan, .gitignore, handoff to a second Claude account |
| `claude-session-2.md` | Chat 2: commit, credential check, first GitHub push |
| `claude-session-3.md` | Chat 3: GitHub verification, transcripts, demo video preparation |

## How to read these

- I write to Claude in Tanglish (Tamil in English letters). Claude replies in the same style.
- The chats are condensed: long terminal output is shortened, and personal, non-technical parts were removed for privacy. The technical content (commands, errors, fixes, decisions) is kept as it was.
- Because I switched Claude accounts after hitting usage limits, the work is split across several chats.

## Decisions I made (not the AI)

- **Similarity threshold 0.73:** tuned on 19 questions (94% hit@6, 100% off-topic rejection).
- **Agent runs with no tools:** retrieval happens in the API, so small local models cannot misuse tools.
- **`clean_query()`:** strips words like "write" and "Ship 30 essay" before retrieval, after essay requests returned poor results.
- **Credential safety:** I caught `auth.json` in a commit and removed it before the first push.
- **Honest limits:** local 7B essay is shorter than target and slow, cloud path untested, 82 of 303 episodes indexed.
