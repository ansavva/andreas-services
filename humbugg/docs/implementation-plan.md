# Humbugg implementation plan

What is built, what is next, and the order it has to happen in. Written for whoever — human or
agent — picks this up next.

**Issues are the source of truth for scope; this file is the source of truth for *order*.** A
GitHub issue says what a thing is. It does not say that #133 must exist before five other things
have anywhere to render, or that #365 gets more expensive every week it waits. That is what this
file holds. When they disagree about scope, the issue wins and this file should be corrected.

Last reconciled against the repo on 2026-08-27.

---

## Where it stands

Live at `https://www.humbugg.com` (product app at `app.humbugg.com`, API at `api.humbugg.com`).

| Milestone | Closed | Open | State |
|---|---|---|---|
| Foundation | 13 | 0 | Complete |
| Free | 3 | 10 | The active milestone |
| Plus | 8 | 1 | Backend complete and deployed; only the purchase UI (#141) remains |
| Work | 0 | 10 | Deliberately untouched |
| Launch | 2 | 11 | Gated on Free |

### How it got out of order, and why that matters

Work jumped from Foundation straight to Plus, so the **paid tier was finished before the free one
existed**. Six PRs of Plus backend — managed invitations, scheduled reminders, co-organizers,
customization, reusable templates, post-draw late-participant reassignment — sat unmergeable for
five weeks, then merged on 2026-08-27 along with the first two pieces of Free.

The consequence is still live and is the single most important thing to understand about this
codebase today: **most of Plus has no user interface.** The backend is complete, tested and
deployed. Almost none of it is reachable, because the organizer surface it would live on (#133) does
not exist and the purchase flow that would sell it (#141) was written against a deleted directory.

Do not read the Plus milestone being nearly closed as "Plus is done".

---

## Critical path

Four issues, in this order. Everything else queues behind them.

### 1. #133 — organizer readiness dashboard ← **the keystone**

Filed under Free, but it is also the only plausible home for five of the six shipped Plus features.
The app has **no organizer surface at all**: the invitation list, reminder settings, co-organizer
management and the template picker have nowhere to render. Build this and the Plus backend stops
being dark.

It reads across wishlist readiness, address readiness, and post-draw progress, which is why it comes
after #127/#128 (done) and pairs naturally with #132.

### 2. #141 — Plus upgrade and purchase experience

Until this exists **nobody can buy Plus**, so none of the shipped backend can earn anything. PR #200
was closed rather than rebased: it targeted `humbugg/frontend/`, which no longer exists. Its intent
is a good specification and the branch `Codex/humbugg-plus-purchase-ux-141` is retained — the
upgrade offer on a `plus_required` refusal, the organizer billing card, and the four checkout-return
states (canceled, paid, failed/expired/refunded, still-confirming).

Re-author for React Native: `StyleSheet` not Tailwind, `Linking`/`expo-web-browser` not
`window.location.assign`, a persistent store not `sessionStorage` for the resume-intent key.

### 3. #130 → #131 → #132 — the rest of the wishlist spine

All three hang off the wish model added in #127. Take them in that order: claims and questions are
independent of each other but both inform what #132 has to display, and #133 renders all three.

**#130 carries a privacy rule that the model was shaped around.** A purchase claim is visible to
every gift viewer and *never* to the wishlist owner. That is why `Wish` and `RecipientWish` are
separate types today despite carrying identical fields — see "Seams that exist for a reason" below.

### 4. #129 — product metadata from wishlist URLs

Deliberately last of the wishlist group. Today a pasted URL is stored as typed, validated as
absolute http(s) and **never fetched**. #129 is the issue that introduces fetching, and with it an
SSRF surface: it needs the blocklist, redirect/size/time limits and sanitisation its acceptance
criteria describe. Nothing else is blocked on it, so there is no reason to take that risk early.

---

## Running alongside

Two items do not queue behind the critical path.

**#365 — decide the app's sign-in mechanism. DECIDED: Managed Login, hosted sign-in and sign-up.**
Implemented August 2026; the record is [`auth-managed-login.md`](auth-managed-login.md).

This entry used to say the choice "replaces the Cognito pool". **It does not, and never did** —
Managed Login changes the app *client* and adds a branding record and a domain; the pool, its schema
and every `sub` in it are untouched. The clock on this ticket was real for a different reason: every
signed-in user is signed out once at cut-over, which at the zero accounts the pool actually held
cost nothing. Part of cross-service epic #363.

**#373 — an authenticated round trip against this machine's dev pool.** The cheapest real safety win
available. Humbugg is the only service with a per-machine dev pool and the test user was seeded in
#372. Today nothing anywhere in this repo proves a signed-in request works, and every app here
degrades *quietly* to signed-out when its pool configuration resolves empty. Part of epic #370.

---

## Then, in order

**Finish Free** — #134, #135, #137 are each partly delivered; their issues carry a comment recording
exactly what exists and what remains, so read that before estimating. #136 (repeat an exchange) and
#138 (mobile and assistive-technology verification) close the milestone.

**Launch** — live Stripe mode (#159), the payment and email matrix (#160), runbooks (#161), the beta
(#162), the checklist (#163), pricing pages (#158), and the three GDPR obligations (#190, #191,
#192). None can start before Free is finished.

**Work** — ten issues, correctly cold. It is two tiers away. Do not start it until a stranger can
complete a Free exchange unaided.

---

## Seams that exist for a reason

Things that look like redundancy and are not. Removing them is how the bug gets in.

**`Wish` vs `RecipientWish`** (`Models/Domain.cs`). Identical fields today. They are separate
because #130 adds purchase claims — visible to every gift viewer, never to the owner — and #132 adds
gift progress. Projecting both audiences through one type makes that leak a one-line mistake.
`RecipientWish` also deliberately drops `CreatedAt`/`UpdatedAt`: when someone last edited their list
is their own business.

**The free-text `wishlist` field was not replaced.** #127 added structured wishes *alongside* it, and
it now carries general preferences ("Likes, sizes and hobbies"). That is why there was no data
migration and why a list written before wishes existed still reaches its giver intact.

**Wishes are keyed `(member_id, wish_id)`.** Listing is a Query, never a Scan, and no single-item
write can address a wish without naming its owner — ownership is structural rather than a check
someone can forget. Three tests attack another member's wish *by its exact real id*.

**A consumer resolves its own settings, not `HumbuggSettings.FromEnvironment()`.**
`EmailArchitectureTests.ConsumersDoNotReadTheApisFullSettingsContract` enforces it. `FromEnvironment`
requires every table the API reads; a scheduled Lambda opens a subset. Calling it in a consumer
couples that Lambda to tables it never touches, so adding one to the API later breaks it at cold
start with an error naming a table it does not use. That is #387 — six days of red prod deploys. See
`AwsLambdaReminderConsumer.SettingsFromEnvironment`.

---

## Traps that have already cost time

**Adding a `RequiredTable` means editing `humbugg-pr.yml` too.** Three PRs added a required table,
updated `humbugg-prod.yaml`, and left the PR workflow's smoke step alone. All three failed
identically: the container threw at startup and `docker run --rm` reaped it before `docker logs`
ran, so CI reported `No such container` and named nothing. `--rm` is gone now, and PR #473 adds a
unit test asserting the smoke env covers every `RequiredTable` call site.

**Merging several PRs to `main` in quick succession drops intermediate deploys.** The prod workflow's
concurrency group is `cancel-in-progress: false`, which queues rather than cancels — but GitHub
keeps only **one** pending run per group, so a third merge cancels the second's queued run. That is
survivable on its own, except `deploy-infra` runs on push *only when the commit touched
`humbugg/infra/**`*, while `update-lambda` proceeds whenever `deploy-infra` is not a **failure** —
and `skipped` is not a failure. A dropped infra deploy therefore surfaces two merges later as
`ResourceNotFoundException: Function not found`. It happened on 2026-08-27 merging the Plus stack.

*If you merge a stack: let each deploy finish before merging the next, or afterwards dispatch
`humbugg-prod.yaml` with `run_infra: true` and check the tables and Lambdas exist.*

**`aria-label` on a control inside `FieldLabel` has no effect.** `FieldLabel` wraps
`DsField.Root`, which supplies the accessible name via `aria-labelledby` from the label text. Put
"(optional)" in the `hint` prop, not the label string — the name should read "Rough price, optional".
`group.tsx` and `settings.tsx` still pass ineffective `aria-label`s; harmless, but misleading.

**A green Expo build proves nothing about which design-system leaf resolved.** Metro considers
`.web.tsx` then `.tsx` for web and never `.native`; an unconfigured export silently takes the *web*
leaves and the app renders entirely unstyled while compiling and passing every test. Run
`node humbugg/scripts/assert-design-system-leaves.mjs native humbugg/app/dist` after an
`expo export -p web --source-maps`. Grepping the bundle for `react-native-web` is not a substitute.

**Run the exact CI commands, not approximations.** `terraform validate` on the prod env only is not
`tflint --recursive`; `dotnet build` is not `dotnet format --verify-no-changes`. Both have failed a
PR that was verified locally the loose way.

---

## Conventions for humbugg work

- Read the `design-system-ui` skill before touching any screen. All UI comes from
  `@ansavva/design-system`, imported from the package root. `humbugg/app` has **no Tailwind**.
- `humbugg/app` is React Native (Metro, `.native` leaf) even in the browser. `humbugg/marketing` is
  Vite and web.
- Wishes, addresses and wishlists are personal data: anything that removes a member must remove
  them too, and the export must carry them. See `docs/data-retention-deletion.md` and
  `docs/gdpr-compliance.md`.
- Every plan-gated capability goes through `PlanCatalog.HasCapability` / `EnsureCapability`, and the
  refusal is a 402 naming what the plan would buy.
- Auditing is never gated on a plan.

## Related documents

- [`../CLAUDE.md`](../CLAUDE.md) — service context, local development, deploys
- [`threat-model.md`](threat-model.md) — invitations, assignments, payments, Work tenancy
- [`gdpr-compliance.md`](gdpr-compliance.md) and [`data-retention-deletion.md`](data-retention-deletion.md)
- [`analytics.md`](analytics.md), [`email-operations.md`](email-operations.md), [`stripe-setup.md`](stripe-setup.md), [`support-email.md`](support-email.md)
