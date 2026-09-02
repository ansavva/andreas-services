# Verifying a Free exchange by hand

The half of #138 a machine cannot hold. Everything mechanical is already automated and named at the
bottom of this file — **run those first**, because a red suite makes this walkthrough a waste of an
afternoon.

This is deliberately short. A checklist nobody runs verifies nothing, so anything a test could
assert has been moved into a test instead of being listed here.

## Before you start

```bash
./humbugg/scripts/dev-up.sh
```

You need **two** accounts to see any of this: the exchange is about what one person may know about
another, and a single account cannot show you a single one of those boundaries. `dev-user.sh` makes
the first; make the second through the hosted sign-up page like a real participant, so that flow is
exercised too.

## The walkthrough

Run it end to end once, as two people, in this order — each step depends on the one above it.

- [ ] **Create** an exchange. Name, currency, spending limit, description.
- [ ] **Share** the invite link. Copy it from the organizer screen; do not hand-build one.
- [ ] **Join** as the second account, from the link, signed out. You should meet the sign-up page,
      not a wall.
- [ ] **Wishlist** — add a wish with a link, one without, reorder them, delete one.
- [ ] **Exclusions** — as organizer, stop the two of you being drawn for each other.
- [ ] **Draw**. With an exclusion that makes a two-person draw impossible, confirm the refusal
      explains itself. Then remove it and draw for real.
- [ ] **Assignment** — each account sees exactly one recipient, and their list.
- [ ] **Questions** — ask anonymously as the giver, answer as the recipient. Confirm the recipient
      is told nothing about who is asking, anywhere on the screen or in the page source.
- [ ] **Gift status** — move through choosing → purchased → sent as the giver, and mark it arrived
      as the recipient. Confirm the giver's own stage is not visible to the recipient.
- [ ] **Repeat** — start next year's exchange from this one. Confirm last year's assignments,
      claims and question threads are all gone rather than merely hidden.

## Assistive technology

Real screen readers, on a real device. Nothing below can be checked in a browser at a narrow width,
which is why it is here and not in `verification.spec.ts`.

- [ ] **VoiceOver (iOS)** and **TalkBack (Android)** — swipe through the group screen and the
      wishlist form. Every control announces what it is and what it does; nothing announces as
      "button" alone.
- [ ] **Focus order follows the page**, not the DOM's convenience. Tab through the organizer screen
      and confirm the order is the order things are read in.
- [ ] **Focus is visible** on every stop, including inside dialogs.
- [ ] **A dialog traps focus** and returns it to whatever opened it on close.
- [ ] **Errors are announced**, not merely coloured. Submit an empty wish title with the screen
      reader on and confirm you are told.
- [ ] **A saved change is announced.** "Saved." must reach a screen reader, not only an eye.
- [ ] **Largest accessibility text size** (iOS Display & Text Size → Larger Text at maximum).
      Nothing may clip or overlap; the layout may reflow as much as it likes.
- [ ] **Reduce Motion** on — no animation is load-bearing.

## Failure and recovery

The paths a person hits on their worst day. Each should say what happened and what to do next —
never a raw status code, and never a dead end.

- [ ] Open an invite link with the `#invite=` fragment removed.
- [ ] Open an exchange you were removed from.
- [ ] Turn off the network mid-save on the wishlist, then restore it.
- [ ] Two browsers, same organizer, both editing exchange settings — the second save must explain
      that it lost rather than silently overwrite.
- [ ] Try to add a seventh participant to a Free exchange. The limit should read as a plan boundary
      with a way forward, not as a failure.

## What is already automated

Do not re-check these by hand; check that they are green.

| Check | Command | Covers |
|---|---|---|
| Accessible names, and the `FieldLabel` trap | `npm run a11y:check` | every control has a name that is not silently overridden |
| Colour contrast | `npm test -- contrast` | WCAG AA on every pair the app paints |
| Mobile widths, keyboard reach, privacy | `npm run e2e -- verification` | 320/390/414px on all four screens; tab reachability; no wishlist, address or token in the console; the signed-out invitation exposing only a name; the invite secret never leaving the fragment |
| Every screen's own behaviour | `npm run e2e` | the eleven other specs |

All four run on every PR.
