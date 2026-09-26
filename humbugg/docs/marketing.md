# Humbugg marketing — positioning and materials

What Humbugg says about itself, where, and why. The site, the app store copy
when there is one, and every ad or reel are written from this page, so a claim
that is not here is not made. Product facts are checked against the code they
describe; the file that owns each is named so the claim can be re-verified.

## Positioning

**Lead with the chat.** Every Secret Santa tool draws names and holds a wish
list. Humbugg is the one where, after the draw, each person has two private
conversations — with the person they drew, and with whoever drew them — and
nobody's cover is blown. It is the feature people have never had, it is the
one that produces a story worth telling, and it is on Free. (Decision
2026-09-15, maintainer: the chat is "one of our biggest selling features" and
leads the site, the materials and this document.)

The one-line positioning: **Ask them anything. Stay a secret.**

Second: the calm draw — wish lists, exclusions, one private assignment, no
group chat. This was the whole pitch until September 2026 and stays the
supporting argument. "Secret Santa, minus the group-chat chaos" survives as the
eyebrow because it contrasts with, rather than contradicts, an anonymous
one-to-one chat.

Third, and only on the pricing page: what Plus adds (invitations by email,
reminders, co-organizers, templates, late joiners).

## What may be claimed about the chat

Each line names the code that makes it true. Rewording is fine; the fact is not.

| Claim | True because |
|---|---|
| Two conversations per person: recipient by name, giver as "Your Secret Santa" | Two tabs, named for the other end (#692). The recipient's name reaches the giver's tab from the assignment they already hold; no prop or path names the giver |
| Humbugg never says who is typing | A message records which SIDE wrote it; the giver is re-derived from the draw on every request and **no stored row carries the giver** — `NoStoredRowCarriesTheGiver` in `backend/Humbugg.Api.Tests` (#131, #692) |
| Messages arrive live | Pushed over `wss://ws.humbugg.com`, poll fallback; the push payload is `{type, group_id, side}` — no body, no name (#697) |
| An optional email says one is waiting, not who from | "You have a message waiting in the anonymous chat about your gift. Humbugg does not say who it is from." Opt-in, non-essential, once per unread stretch (#692, `docs/email-operations.md`) |
| One switch turns it off | The recipient's "Allow questions" switch; off refuses both sides (#717). Only the recipient holds it — a giver who could block or unblock would defeat the control |
| Included in Free | `marketing/src/pages/PricingPage.tsx` lists it under Free; no `HasCapability` gate on the question routes |

**Do not claim:**

- "Nobody can ever find out." The organizer holds an emergency reveal
  (`docs/runbooks.md`), and a draw reset invalidates threads. Say *Humbugg
  never says who is typing*, which is exactly what the code enforces.
- "Unlimited" or "forever". Threads are draw-scoped, and
  `docs/data-retention-deletion.md` forbids advertising retention.
- Anything about the organizer reading the chat. They cannot, but "not even
  the organizer" invites the reveal question above.
- "Moderated", "safe" or "report abuse". There is no moderation, reporting or
  organizer visibility; the recipient's switch is the only recourse
  (`docs/threat-model.md`, RR7 still open).

## Brand assets

Two logo forms, and both are files now (decision 2026-09-15). Never retype the
wordmark: it is Lily Script One at `-0.025em`, and a re-render in another
weight or face is not the logo.

| Form | File | Use |
|---|---|---|
| **The mark** — dark green rounded square, white script H | `app/assets/images/icon.png` (512) | app icon, favicons, the reel's hook pill, anywhere the name is already said |
| **The wordmark** — "Humbugg" in Lily Script One, brand green | `marketing/public/brand/humbugg-wordmark.svg` / `.png` | headers, end cards, print; served at `www.humbugg.com/brand/…` |
| The wordmark on dark | `marketing/public/brand/humbugg-wordmark-cream.svg` / `.png` | over photography or green |
| **The lockup** — mark beside wordmark | `marketing/public/brand/humbugg-lockup.png` | social previews, partner pages |

The SVGs embed the font, so they render identically without it installed.
Colours: green `#1d5545`, cream `#fffdf8`, ink `#18332b`. **The shipped icon set is
not on that green**: `app/assets/images/icon.png`, the splash and every favicon are
`#173f0c`, a darker, yellower green than the token the wordmark and the whole UI use.
The lockup here and the reel recolour the mark to `#1d5545`; the icon files themselves
are an open decision (found 2026-09-15 when the two greens met on the reel's end card). The marketing site's
social preview (`marketing/app/assets/og.png`, 1200×630) is the wordmark as the
heading with the anonymous chat under it, and nothing else (maintainer's call,
2026-09-15: no mark beside the wordmark, no headline, no footer line). **The chat
is a screenshot of the real rail, not a drawing**: the app's stubbed Playwright
export (`humbugg/app`, `npx playwright test`) with a drawn exchange stubbed the
way `e2e/questions.spec.ts` does, three messages seeded, the recipient's
"Your Secret Santa" conversation open, viewport 1440×680 at 2×, the rail
cropped from the page and the empty stretch above the composer removed. Redo
it the same way when the chat UI changes. The card-game image it replaced was
a generated mock and is gone.

## Where it is said

| Surface | What carries the chat | File |
|---|---|---|
| Landing hero | subtitle's last clause; step 03's last clause | `marketing/src/pages/LandingPage.tsx` |
| Landing "The chat" section | heading, mock conversation, three proof lines, "Included in Free." | same; pinned by `LandingPage.test.tsx` |
| Pricing, Free plan | "An anonymous chat with your recipient — and with your own Santa" | `marketing/src/pages/PricingPage.tsx` |
| `<meta description>` / `og:description` | one clause each | `marketing/app/routes/_index.tsx` |
| JSON-LD description | one clause | both pages |
| Instagram Reels | the first commercial, below | outside the repo |

The prod smoke test greps `www.humbugg.com/` for `More wonder` — the H1 is
load-bearing for deploys, so keep it, or change the grep in the same PR
(`.github/workflows/humbugg-prod.yaml`).

## Channels

**Instagram Reels, organic, first.** No paid placement until a reel has held
an audience on its own; paid Meta creative also brings alcohol-targeting and
suggestive-content policy into play, which the first creative deliberately
avoids relying on.

Reel spec, verified 2026-09-14:

| | |
|---|---|
| Frame | 9:16, 1080×1920, MP4/MOV, H.264, 30 fps, ≤4 GB |
| Length | aim 10–15 s; retention is ranked on *completion*, so shorter wins |
| Safe zones | top ~250 px and bottom ~340 px free of text and logos (IG chrome) |
| Sound | designed sound-on, delivered sound-off: hook as on-screen text at frame one, captions on every spoken word |
| CTA | organic reels cannot link — "Free · Link in bio", never a URL to tap |

## How a short-form spot is written

**The method is the `short-form-ad` skill** (`.claude/skills/short-form-ad/`):
hook formulas, structure by length, sound-off rules, platform specs, the
pre-render checks and the deliverable template. Load it before writing any
script. The points from that research that changed this one:

- The hook decides 60–80 % of performance. Viewers decide inside 3 s; 3-second
  retention above 65 % earns 4–7× the impressions.
- 10–14 words, delivered inside 2 s, then expanded for 3–5 s. Specific beats
  vague.
- Three triggers, use two: **pattern interrupt** (visual), **curiosity gap**
  or **contrarian claim** (words), social proof.
- Something moves in the first second. A static open is a swipe.
- Under 15 s the structure is **Hook → Solution → CTA**. The "problem" beat
  only exists in 30 s cuts.
- Body copy is byte-identical across hook variants, so an A/B result means
  something.

## The first commercial (September 2026)

**Brief.** A Santa figure, off duty in a loft workshop, coffee in one hand and
phone in the other, tells the camera about the chat. The visual is the pattern
interrupt; the words carry the contrarian claim. 14 s of dialogue plus a
3 s end card.

**Script v2** (37 words, ~14 s):

> **Hook** "Secret Santa's one problem? You can't ask them anything without blowing your cover."
> **Solution** "Humbugg has a chat. Text your person. They text their Santa back. Nobody finds out it's you. Not even me."
> **CTA** "Humbugg. Free. Link in bio." *(sips)*

On-screen at frame one: **"Text your Secret Santa. Stay secret."** End card:
wordmark on cream, "Free · Link in bio".

Alternate hooks, same body, for a second cut: *"You're about to draw your own
mother in Secret Santa. Again."* (mistake warning) · *"Organisers of the
office Secret Santa: this one's for you."* (identity).

**Production.** AI-generated; the character is not named here. Frame-first: a still is
iterated at cents, then one Seedance 2.0 image-to-video run with native
lip-synced audio, 9:16, 1080p, fixed seed, from the approved still. Text
overlays, captions, end card and music are added locally afterwards; clips were
joined with nothing added. Alcohol references were edited out of
the still before animating so the same asset can later run paid without a
re-shoot. Costs at the time: a still edit ≈ $0.13; a 14 s 1080p Seedance take
≈ $5–10.

**Status (2026-09-15).** Take 4 rendered on Seedance 2.5 and filed as the project's
`reel-chat` scene. Assembled locally with HyperFrames: hook text at the belt line,
word-timed captions in the safe band, 3 s end card, 1080×1920 H.264 30 fps, 19.1 s.
Draft v1 delivered; music undecided (none in v1). Lessons: Seedance refuses a first
frame wider than ~900 px with a misleading "sensitive" error, so animate from a 720 px
copy; a hand going to the mouth turns a held phone into a cup, so the sip was dropped;
the caption engine's themes are 16:9-tuned, so captions were built in the composition.

## Open

- **Question threads are missing from the GDPR data export**
  (`backend/Humbugg.Api/Services/DataExportService.cs` exports profile,
  memberships, wishlist, avoidances, address and claims; not questions).
  Deletion covers them; export does not. Leading the marketing with the chat
  makes this the first thing a subject-access request would test — fix before
  the reel goes out. Found 2026-09-15 while writing this page.
- No abuse path beyond the recipient's switch. Acceptable for a private
  exchange among people who know each other; revisit before any Work tier.
- A short screen recording or still of the real chat for the site and the
  reel's end card — the mock conversation on the landing page is placeholder
  copy.
- App-store listing copy, when the native builds ship: lead with the chat.
- Whether the hero H1 should move to the chat line. Not yet — the smoke grep
  and the OG image both carry "More wonder."

## Sources

- OpusClip, *TikTok hook formulas* — <https://www.opus.pro/blog/tiktok-hook-formulas>
- Reloop, *UGC script templates and 20 hook formulas* — <https://reloop.so/blog/article/ugc-script-templates/>
- Teleprompter, *The 3-second rule* — <https://www.teleprompter.com/blog/tiktok-3-second-rule>
- Sovran, *TikTok creative best practices 2026* — <https://sovran.ai/blog/tiktok-creative-best-practices>
- Strike Social, *Instagram ad specs 2026* — <https://strikesocial.com/blog/instagram-ad-specs/>
- Get Ryze, *Meta ad sizes and safe zones* — <https://www.get-ryze.ai/blog/facebook-ad-sizes-complete-specs-guide-for-2026>
