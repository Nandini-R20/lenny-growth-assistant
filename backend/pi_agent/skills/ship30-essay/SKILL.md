---
name: ship30-essay
description: Turn grounded answers from Lenny's Podcast transcripts into a Ship 30 for 30 style essay of about 1,250 words. Use when the user asks for an essay, newsletter, post, article or Ship 30 piece.
---

# Ship 30 for 30 essay skill

You write a skimmable, online-first essay (about 1,250 words, acceptable range 1,100 to 1,400) using ONLY the excerpts in the `<sources>` block of the user message. These rules come from the Ship 30 for 30 "Ultimate Guide to Start Writing Online" by Nicolas Cole and Dickie Bush. Read `references/principles.md` only if you need the reasoning behind a rule; you can write the essay from this file alone.

## Grounding (never break these)
- Every claim, number, and story comes from the excerpts. Cite with [n] after the sentence that uses it.
- Never invent anecdotes, statistics, quotes, or guests. If the excerpts are thin, write a shorter essay and say in the last line what the transcripts did not cover.
- Credibility type is always "curating the experts": name the guest ("Todd Jackson says...") instead of speaking as the expert yourself.

## Process (do this silently, then output only the essay)
1. Pick ONE narrow topic from the request. Name the audience and the outcome (for example "early-stage PMs who want to hire a head of growth").
2. Pick ONE lens: Actionable (how to), Analytical (what the numbers or evidence say), Aspirational (it can be done), or Anthropological (why people behave this way). Default to Actionable.
3. Pick ONE proven approach to organize the main points: Steps, Lessons, or Mistakes. Use the same pattern for every main point.
4. Tequila test: skip the obvious conventional advice. Lead with the least obvious, most specific insight found in the excerpts.

## Structure and word budget
1. **Headline** (about 15 words). Answers WHO it is for, WHAT it is about, WHY read it (the promise). Specific and clear, not clever. Keep the promise, no clickbait.
2. **Hook introduction** (about 120 words). Open with one short punchy sentence, then three sentences that clarify the problem and name the credibility (which guest or guests you are drawing on), then one short closing sentence that promises what the reader gets. Include one short true story or moment from the excerpts if one exists (answer the question AND tell a story).
3. **Five main points** (about 190 words each). Each starts with a bold, skimmable subheading in the chosen pattern ("Lesson 1: ..."). Inside each point alternate rhythm: short line, a longer explanation of 3 to 4 sentences, then a short closing line. Use a bulleted list whenever you are listing things. Bold only the one sentence per point that matters most.
4. **Takeaway** (about 100 words). One specific, useful thing the reader can do this week, plus a one-line TL;DR of the main points.
5. **Sources** list: "[n] Guest, episode title" for every source number you cited.

## Style rules
- Rate of revelation: every sentence must add something new. Cut filler and repetition.
- Rhythm: alternate short and long sentences and paragraphs. Never write many one-line paragraphs in a row, and never write long blocks of 5+ sentences.
- Skimmable: subheadings, bullets, selective bold. A reader skimming only the headings should still get the argument.
- Plain words. No hype.

## Output format
Reply with one short sentence, then the whole essay inside one block:
<artifact type="markdown" title="the headline"> ...essay in Markdown... </artifact>
