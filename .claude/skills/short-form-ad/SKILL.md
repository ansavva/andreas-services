---
name: short-form-ad
description: >-
  Write a short-form commercial — an Instagram Reel, a TikTok, a YouTube Short —
  for any product in this monorepo: the hook, the script, the on-screen text,
  the end card and the platform spec, in that order, before anything renders.
  Use whenever a task says commercial, ad, reel, promo, hook, script, TikTok,
  Instagram, or "make a video that sells X". It owns the WORDS and the
  structure; rendering is handed to aperture (an AI-generated talking head) or
  HyperFrames (captions, overlays, end card). Read before writing a single
  line of dialogue: the first three seconds decide most of the outcome, and
  the instinctive opening line is the wrong one.
---

# short-form-ad — the script is everything

A short-form ad is judged in three seconds and ranked on completion. Every rule
below follows from those two facts. The method: **hook first, then structure,
then words, then the spec, then render.** Writing the body first and bolting
a hook on afterwards is the failure mode this skill exists to prevent.

Researched September 2026 for Humbugg's first reel; sources at the end. The
numbers are what the sources agree on, not one site's claim.

## The numbers that shape everything

| Fact | Consequence |
|---|---|
| Viewers decide to stay or swipe inside **3 s**; many inside 1.7 s | The hook is delivered by second 2 and expanded by second 5 |
| The hook accounts for **60–80 %** of performance variance | Spend the writing time here, not on the body |
| 3-second retention above **65 %** earns **4–7×** the impressions | Losing more than a third of viewers by second 3 kills distribution |
| Ranking is on **completion rate**, not total watch time | Shorter wins. 15 s at 80 % beats 40 s at 50 % |
| Most viewers watch **muted** | Every message must also be on screen, from frame one |
| Something must **move in the first second** | A static open reads as a photo and is swiped |

## Structure, by length

| Length | Beats | Seconds |
|---|---|---|
| **≤ 15 s** (organic reels, the default here) | **Hook → Solution → CTA** | 0–3 · 3–11 · last 3 |
| 30 s (paid, conversion) | Hook → Problem → Solution → CTA | 0–3 · 3–10 · 10–25 · last 3–5 |
| 45–60 s (YouTube Shorts) | the 30 s shape, with proof in the solution | viewers are more patient there |

Under 15 s the **problem beat is cut**, not compressed. The hook carries the
tension on its own. If the piece needs a problem section, it is a 30 s piece.

Spoken pace for a talking head is about **3 words per second**. A 14 s clip is
~40 words including pauses; a 10 s clip is ~28. Count before rendering — a
video model told to fit 50 words into 12 s compresses or drops them.

## The hook

**10–14 words, specific, delivered inside 2 seconds.** Then 3–5 seconds
expanding on it. Vague promises kill retention: replace "better results" with
the concrete thing.

Three psychological triggers; a good hook uses **two**:

1. **Pattern interrupt** — a visual the feed does not expect. Usually carried
   by the image, not the words.
2. **Curiosity gap / contrarian claim** — a statement the viewer cannot resolve
   without watching. Usually carried by the words.
3. **Social proof** — evidence, numbers, a result.

The three formulas the sources call most reliable right now: **contrarian
claim**, **mistake warning**, **list tease**. The full catalogue:

| Formula | Template | Example |
|---|---|---|
| Contrarian | "[Common belief] is wrong." | "Secret Santa's one problem? You can't ask them anything without blowing your cover." |
| Mistake warning | "You're about to [specific mistake]." | "You're about to draw your own mother in Secret Santa. Again." |
| Identity | "If you're [identity], this is for you." | "Organisers of the office Secret Santa: this one's for you." |
| Bold statement | Declarative claim, credibility in the next frame | "Most creators are killing their reach with captions." |
| Question (not yes/no) | "Why do [X] while [Y]?" | "Why do some TikToks go viral at 200 views and others die at 20,000?" |
| Proof-first | Show the result, then tease how | "I grew this from 0 to 50,000 in 90 days." |
| Result | "I [result] in [timeframe]." | |
| Curiosity | "I tested [X] for [duration] and…" | |
| Shock | "Stop [behaviour] until you see this." | |
| POV | "POV: you finally found [thing]." | |
| Mistake (own) | "The mistake I made with [X]." | |
| Comparison | "I tried [N]. Only one was worth it." | |
| Urgency | "If you're still doing [X], you're losing [Y]." | |
| Authority | "As someone who [credible signal]…" | |
| Transformation | "[Before] to [after]." | |
| Relatable | "Tell me why I didn't find this sooner." | |
| Number / list tease | "[N] things nobody tells you about [X]." | |
| Confession | "I spent [amount] before finding this." | |
| Discovery | "I didn't expect to be talking about [X]." | |
| Validation | "[Person] asked what I changed." | |
| Statistic | "[Stat]. Here's what I did." | |
| Skeptic | "I thought [category] was a gimmick until…" | |
| Challenge | "I challenged myself to [X]." | |

**The weakest opening is the relatable-generic**: "Every year, same thing…",
"We've all been there…". It is the line that comes first to mind and it is a
swipe. If the draft opens that way, rewrite the hook before anything else.

**Write two or three hooks, keep the body byte-identical, and test.** A
result only means something when the hook is the single variable.

## The body and the CTA

- **Solution beat:** name the thing, then three concrete nouns at most.
  "Wish lists. No-gos. One private draw." Not a feature list.
- **One angle, not five.** A reel sells one idea. A second idea is a second
  reel.
- **A button on the last line.** A sip, a look, a shrug — a physical beat that
  lands the last word and gives the cut somewhere to go.
- **The CTA is specific and platform-true.** Organic Reels and TikToks cannot
  link out: say **"Free · Link in bio"**, never a URL to tap. Paid placements
  carry a real button, so the CTA names the action ("Start your exchange").
  "Check it out" is dead everywhere.

## Sound-off design

- **The hook goes on screen as text at frame one**, before a word is spoken.
  Short, not the spoken line verbatim: the spoken hook is 12 words, the
  on-screen one is 5.
- **Captions on every spoken word.** Verbatim; `embedded-captions` renders
  them. The quiet `anchor` identity is the default for a talking head.
- **Text sits in the safe band**: clear of the top ~250 px and bottom ~340 px
  of a 1920-tall frame (platform chrome), and clear of the face.
- **An end card** of about 3 s: wordmark, one line, the CTA. Brand colours
  from the product's theme, not new ones.

## Platform spec

| | Instagram Reels | TikTok In-Feed | YouTube Shorts |
|---|---|---|---|
| Frame | 9:16, 1080×1920 | 9:16, 1080×1920 | 9:16, 1080×1920 |
| Container | MP4/MOV, H.264, 30 fps, ≤4 GB | MP4/MOV, H.264 | MP4 |
| Length that works | 10–15 s organic; ads 15–90 s allowed | 15–30 s for conversion ads | up to 60 s |
| Safe zones | top ~250 px, bottom ~340 px | similar | similar |
| Link in CTA | organic no; paid yes | organic no; paid yes | no |

Verified 2026-09-14; re-check before a paid buy, these move.

## Brand and policy checks before rendering

Run through these on the **still**, before video money is spent — a still is
cents, a clip is dollars, and a rejected ad is a total loss.

- **Alcohol** anywhere in frame (a can, a label, a chalkboard line) forces
  age-restricted targeting on paid Meta placements. Edit it out of the still.
- **Suggestive framing** is fine organic, risky paid. Decide the channel first.
- **Music:** the platform's audio library is licensed only for organic posts
  made in the app. A paid ad, or any export, needs a track you hold rights to.
- **Claims:** every product claim in the script must be one the product's
  documentation allows. Humbugg's is `humbugg/docs/marketing.md` ("What may be
  claimed"); write the equivalent page before the first ad for any other
  service.
- **Rendered text in an AI still will garble under motion.** Keep the camera
  move slow and single, and put nothing load-bearing in in-frame signage.

## The deliverable, before anything renders

Show the user this, filled in, and get a yes on the script before a still or
a clip is bought:

```
Channel:        organic Instagram Reel | paid Meta | TikTok | Shorts
Length:         14 s dialogue + 3 s end card
Hook (spoken):  "…"                       ← 10–14 words, formula: contrarian
Hook (screen):  "…"                       ← ≤6 words, frame one
Solution:       "…"                       ← ≤3 concrete nouns, ~20 words
CTA:            "…"                       ← platform-true
Button:         the physical beat on the last line
End card:       wordmark · one line · CTA
Alt hooks:      A "…" (mistake warning)  B "…" (identity)   — body identical
Checks:         alcohol ✓  suggestive ✓  music ✓  claims ✓  word count ✓
```

## Handing off to render

This skill stops at the words. The picture is someone else's:

| Need | Skill |
|---|---|
| An AI-generated talking head from an approved still, lip-synced | aperture, Seedance image-to-video (dialogue in double quotes drives the audio; ≤15 s; `generate_audio: true`; fix the `seed` so a retake is comparable). Show the payload, submit only when told |
| Captions on the finished clip | `embedded-captions` |
| Hook text, overlays, the end card, music, the 1080×1920 export | `motion-graphics` or `general-video` (HyperFrames) |
| A product-UI or website-driven promo with no talking head | `product-launch-video` |

## Worked example — Humbugg's first reel (September 2026)

Product: an anonymous chat between a Secret Santa giver and recipient. Visual
pattern interrupt: an off-duty Santa figure in a loft workshop, coffee and
phone. Words: contrarian claim. 37 words, 14 s, Seedance from an approved
still, organic Instagram Reel.

> **Hook** "Secret Santa's one problem? You can't ask them anything without blowing your cover."
> **Solution** "Humbugg has a chat. Text your person. They text their Santa back. Nobody finds out it's you. Not even me."
> **CTA** "Humbugg. Free. Link in bio." *(sips)*

On-screen at frame one: "Text your Secret Santa. Stay secret." The first draft
opened with "Every year, same thing…" and was thrown out for the reason above.
The full brief, the claims table and the status live in
`humbugg/docs/marketing.md`.

## Sources

- OpusClip — <https://www.opus.pro/blog/tiktok-hook-formulas>
- Reloop, 10 structures and 20 hook formulas — <https://reloop.so/blog/article/ugc-script-templates/>
- Teleprompter, the 3-second rule — <https://www.teleprompter.com/blog/tiktok-3-second-rule>
- Conbersa, hook formulas for founders — <https://www.conbersa.ai/learn/tiktok-hook-formulas-for-founders>
- Retiplex, UGC ad script guide — <https://www.retiplex.com/blog/ugc-ad-script-guide>
- Sovran, TikTok creative best practices 2026 — <https://sovran.ai/blog/tiktok-creative-best-practices>
- Stackmatix, TikTok ad creative 2026 — <https://www.stackmatix.com/blog/tiktok-ad-creative-best-practices-2026>
- Strike Social, Instagram ad specs 2026 — <https://strikesocial.com/blog/instagram-ad-specs/>
- Get Ryze, Meta ad sizes and safe zones — <https://www.get-ryze.ai/blog/facebook-ad-sizes-complete-specs-guide-for-2026>
