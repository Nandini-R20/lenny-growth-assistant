# Design

## Product principles
1. **Receipts over fluency.** Every claim has a citation chip; every chip opens the exact moment in the episode. A confident answer without evidence is worse than "not covered".
2. **Honest about waiting.** Local models on a CPU are slow. The UI shows the phase (searching, reading N excerpts, writing), elapsed seconds and a stop button, never a bare spinner.
3. **Make answers reusable.** One sentence turns a conversation into a checklist, a page or an essay in a side viewer.
4. **Calm failure.** Errors say what happened and what to do next, with a retry.

## Visual design: "Editorial"
The goal was a reading tool, not a generic chat skin: no purple gradients, no stock card grids.

| Element | Choice | Reason |
|---|---|---|
| Palette | paper `#F6F1E7`, ink `#1B1A17`, accent burnt orange `#C2410C`, citation green `#0F5C4D` | Warm, high-contrast reading surface; orange for action, green reserved for evidence |
| Dark mode | ink background `#14130F`, accents lightened | Same hierarchy, readable at night |
| Type | Fraunces (display), Newsreader (reading text), Instrument Sans (UI), JetBrains Mono (metadata) | Serif body for long reading, mono for numbers and timestamps; system fallbacks keep it usable offline |
| Texture | very light paper grain | Subtle depth without images |
| Layout | sidebar (chats) / chat column (about 700 px) / artifact panel that slides in | Optimal line length; the viewer never covers the conversation on desktop |
| Mobile | sidebar and viewer become overlays | One column, large touch targets |

## Interaction design
- **Citation chips** (`[1]`): hover or focus shows guest, episode, timestamp and quote; click opens YouTube at that second. Matching source card highlights.
- **Source cards** under each answer: guest, quote preview, timestamp, similarity bar.
- **Model toggle**: segmented control showing the real model id. Cloud is disabled, with the reason, when no key is configured.
- **Artifact viewer**: opens live while the document is written (source view), switches to Preview when complete; tabs for Preview/Source, Copy, Download. HTML preview is sandboxed and shows what the sanitizer removed.
- **"Not covered" state**: calm card plus three suggested questions instead of an error.
- **Empty state**: one headline and four example prompts covering Q&A, a topical question, an essay and an artifact.
- **Keyboard**: Enter sends, Shift+Enter newline, Esc closes popovers and the viewer; visible focus rings.

## Motion
Messages rise and fade (220 to 350 ms), source cards stagger in, similarity bars grow, the viewer slides with an ease-out curve, a caret pulses while streaming, a shimmer marks "thinking". All motion is disabled under `prefers-reduced-motion`.

## Accessibility
Contrast checked for both themes; `aria-live` on the thread; buttons and chips are real buttons with labels; the layout reflows without horizontal scroll down to 360 px.

## Writing skill design (Ship 30 for 30)
The skill encodes the guide's framework as rules the model can follow: pick one narrow topic with a named audience and outcome; one of four angles (actionable, analytical, aspirational, anthropological); one repeated pattern (steps, lessons or mistakes); a headline that states who, what and why; a 1/3/1 hook; five subheaded points with alternating sentence rhythm and selective bold; a specific takeaway. Adaptation for this product: credibility is always "curating the experts", and every story and number must come from the cited excerpts. The reasoning table lives in `backend/pi_agent/skills/ship30-essay/references/principles.md`.

## Trade-offs made on purpose
- Plain HTML/CSS/JS instead of a framework: no build tooling on a locked-down Windows machine, tiny payload, easy to read in an interview.
- A sample of 82 episodes indexed instead of all 303 because indexing on CPU would take hours.
- Router is rules, not an LLM, to keep behavior predictable and fast.
- Local 3B model as the default for speed; 7B and cloud are one setting away.
