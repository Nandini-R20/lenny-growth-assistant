"""Deterministic intent routing. Predictable, testable, and free (no LLM call needed to decide).

Routes:
  qa       - grounded question answering (default)
  essay    - Ship 30 for 30 skill (long-form, ~1,250 words)
  artifact - Markdown / HTML document rendered in the artifact viewer
"""
import re

ESSAY_RE = re.compile(
    r"\b(essay|ship\s?-?30|newsletter|blog\s?post|article|atomic essay|long[- ]form post)\b", re.I)
CREATE_RE = re.compile(
    r"\b(create|make|build|generate|draft|write|design|produce|turn|convert|put|give me|prepare)\b", re.I)
ARTIFACT_RE = re.compile(
    r"\b(artifact|html|web\s?page|landing page|one[- ]?pager|cheat\s?sheet|checklist|template|table|"
    r"infographic|markdown|document|doc|playbook|dashboard|poster|handout|summary page|"
    r"page|brief|framework card|scorecard|outline|plan)\b", re.I)
PRONOUN_RE = re.compile(r"\b(that|this|it|these|those|above|previous|earlier|same)\b", re.I)

ROUTES = ("qa", "essay", "artifact")


def classify(message: str) -> str:
    """Return 'essay', 'artifact' or 'qa'."""
    text = message.strip()
    if ESSAY_RE.search(text) and CREATE_RE.search(text):
        return "essay"
    if CREATE_RE.search(text) and ARTIFACT_RE.search(text):
        return "artifact"
    if re.match(r"^\s*(ship\s?-?30|essay)\b", text, re.I):
        return "essay"
    return "qa"


def needs_context(message: str) -> bool:
    """Follow-ups like 'turn that into a checklist' lean on the previous turn."""
    return len(message.split()) < 9 or bool(PRONOUN_RE.search(message))
