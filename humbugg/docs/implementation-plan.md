# Humbugg implementation plan

What is built, what is next, and the order it has to happen in. Written for whoever — human or
agent — picks this up next.

**Issues are the source of truth for scope; this file is the source of truth for *order*.** A
GitHub issue says what a thing is. It does not say that #133 must exist before five other things
have anywhere to render, or that #365 gets more expensive every week it waits. That is what this
file holds. When they disagree about scope, the issue wins and this file should be corrected.

Last reconciled against the repo on 2026-09-02.

---

## Where it stands

Live at `https://www.humbugg.com` (product app at `app.humbugg.com`, API at `api.humbugg.com`).

| Milestone | Closed | Open | State |
|---|---|---|---|
| Foundation | 13 | 0 | Complete |
| Free | 6 | 7 | The active milestone |
| Plus | 8 | 1 | Backend complete and deployed; the purchase UI (#141) is **built**, awaiting review |
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

### 1. #133 — organizer readiness dashboard ← **the keystone** · **built**

`GET /api/groups/{id}/readiness`, organizer-only and ungated by plan, rendered at
**`/organize/{groupId}`** in the app. The organizer surface the other five things needed now exists;
the invitation list, reminder settings, co-organizer management and the template picker have
somewhere to render, and wiring them there is what stops the Plus backend being dark. That wiring is
**not** done — #133's own acceptance criteria did not cover it.

What the dashboard reports: joined and participating counts, wishlist readiness, address readiness,
whether each participant has opened their match since the draw, and one nudge list combining
outstanding participants with unaccepted invitations. Every state is decided by the server and the
app only renders its label, so "ready" cannot come to mean two things.

Two acceptance criteria are **not** met, both deliberately:

- **Purchased / sent / received.** That is #132's data. The API sends `gift_progress: null` and the
  panel says "not tracked yet" rather than reporting three zeroes, which would be a false claim
  rather than a missing one. The contract and the panel are in place for #132 to fill.
- **"Works for each Work exchange."** It is not plan-gated and works for a Work exchange that
  exists, but see the Work note under "Seams" — the wish roll-up is O(participants) queries, which
  is nothing at 6 or 50 and far too much at 10,000.

### 2. #141 — Plus upgrade and purchase experience · **built**

Plus can now be bought. `humbugg/app/src/components/plus.tsx` holds the offer, the checkout round
trip and the organizer's billing area, rendered at **`/organize/{groupId}`** under the readiness
dashboard, plus a reusable `PlusRefusalCard` the group screen raises the moment any action is
refused with `plus_required`.

Three things about it are decisions rather than details:

- **No price is stated in the app.** Everything numeric — the amount, the currency, the Free and
  Plus ceilings — comes from `GET /api/plans`, which reads the same configuration Stripe charges
  against. A hardcoded "$12" would go on rendering after a price change.
- **"Plus is active" means the ENTITLEMENT exists, never `status: paid`.** The webhook writes the
  entitlement and the group's plan in one transaction and `PlanCatalog.HasCapability` reads the
  entitlement, so a paid row without one is a purchase Stripe has taken money for and Humbugg has
  not applied. The screen says that, rather than promising a capability the next request 402s.
- **Native does not use a return URL.** An `https://` success URL cannot re-enter the app, so
  Checkout opens in the system browser and closing it is the whole signal to re-read the purchase.
  The API is the source of truth on both platforms; `?checkout=` is a hint about what Stripe told
  the browser.

PR #200 was closed rather than rebased — it targeted the deleted `humbugg/frontend/` — and the
branch `Codex/humbugg-plus-purchase-ux-141` was kept for its specification, which this follows.

*Not covered here:* live Stripe mode is still blocked (#159), so an environment whose Plus plan
carries no `price_id` gets "Plus is not on sale yet" instead of a button whose only outcome is a
409.

### 3. #130 → #131 → #132 — the rest of the wishlist spine · **complete**

All three hang off the wish model added in #127. Claims and questions are independent of each other
but both inform what #132 has to display, and #133 renders all three. All three are built, and the
readiness dashboard's gift-progress panel is filled in — as counts, never as names.

**#132 is two facts about one gift, owned by two people, and that shape is the decision.** The
giver's stage (`choosing`/`purchased`/`sent`) lives on their own row; the recipient's "it arrived"
lives on the **giver's** row, written there by inverting the draw so the recipient never learns whose
row it was. A single four-state enum would either refuse the gift handed over at a party — which is
never marked sent — or let a recipient overwrite the giver's record of what they actually did. The
only ordering rule enforced is the one that is actually true: a gift somebody has confirmed
receiving was obviously bought, so the giver cannot walk the stage back afterwards.

Unlike a purchase claim, gift progress **is** audited — safely, because every row targets the ACTOR
and carries a stage. A row naming the other party would be the draw assignment, in the one table an
organizer may read.

**#131's anonymity is structural, and that is the thing to preserve.** No row in
`humbugg-prod-questions` stores the giver: a message records which SIDE wrote it, and every request
re-derives who the giver is from the draw. So there is no field for a projection to leak, no id for
a URL to carry, and nothing for a later endpoint to expose by returning a whole record. Both parties
also receive the byte-identical payload — if the two views were separate projections, one of them
would eventually differ by an identity. The notification names neither party and quotes no body, for
the same reason `AssignmentAvailable` refuses to carry a recipient's name.

*One honest limit:* a notification only sends when an address is on file, which today means the
person joined through a managed (Plus) invitation. Humbugg stores no email on the profile and the
access token carries one only for the caller, who is not the other side of the conversation. On a
Free exchange the thread works and the mail usually does not go — the app shows it either way.

**#130 is built, and its privacy rule turned out to decide the storage.** A purchase claim is
visible to the assigned giver and *never* to the wishlist owner. It is stored on the **claimant's
own membership row**, keyed by wish id and scoped to a draw id, rather than on the wish: a wishlist
owner never reads another member's private membership fields, so there is no projection to get
wrong and no future endpoint to forget. `Wish` and `RecipientWish` are no longer identical —
`RecipientWish` carries `Claim` and `Wish` must never grow it.

Confirmed with the maintainer on 2026-09-02: **a wishlist is visible to the assigned giver and
nobody else.** So "other authorized gift viewers can see that an item is claimed" is satisfied
trivially — there is exactly one such viewer per recipient per draw — and the feature's real value
is the giver's own tracking plus the substrate #132 aggregates. Broadening who may read a wishlist
would be a separate product change, not part of #130.

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

*One thing Work now inherits:* the readiness dashboard counts wishes with one DynamoDB Query per
participant, because the wishes table has no group index — `member_id` is the partition key
precisely so no wish can be addressed without naming its owner, and indexing wish content to build
an organizer roll-up would trade that away. Ten at a time over 6 or 50 participants is nothing; over
Work's 10,000 it is not. Work needs a stored per-member count before it ships, not a GSI over the
wishes.

---

## Seams that exist for a reason

Things that look like redundancy and are not. Removing them is how the bug gets in.

**`Wish` vs `RecipientWish`** (`Models/Domain.cs`). No longer identical: `RecipientWish` carries
`Claim` (#130) and `Wish` must never grow it, because a claim on your own list would tell you what
your giver has already bought. #132's gift progress lands on the same side. Projecting both
audiences through one type makes that leak a one-line mistake. `RecipientWish` also deliberately
drops `CreatedAt`/`UpdatedAt`: when someone last edited their list is their own business.

**Neither a purchase claim nor a question is ever audited.** Every other sensitive action is. An audit row carries the
actor and the target, so recording "this member claimed a wish belonging to that member" would write
the draw assignment into the one table an organizer is allowed to read — and for a question it would
write the giver's identity into it, which the whole feature exists to withhold. Auditing is never
gated on a plan, and it is also never allowed to be the thing that spoils the exchange.

**The free-text `wishlist` field was not replaced.** #127 added structured wishes *alongside* it, and
it now carries general preferences ("Likes, sizes and hobbies"). That is why there was no data
migration and why a list written before wishes existed still reaches its giver intact.

**`requires_address` is a group setting, not a guess.** The readiness dashboard cannot ask whether
everyone has given a mailing address without knowing whether this exchange posts its gifts. An
exchange handed over at a party never needs one, and reporting every participant as "missing an
address" would train the organizer to ignore the column. The organizer sets it from the dashboard;
off by default, and off means the address column reads `not_required` rather than `missing`.

**Assignment views are recorded on the membership row, not read back from analytics.**
`assignment_viewed_draw_id` is written the first time a member opens their match. Analytics already
tracks the same milestone and cannot answer this: it is deduplicated, and `HUMBUGG_ANALYTICS_ENABLED
=false` switches it off — a product surface must not change meaning when telemetry is disabled.
Storing the **draw id** rather than a flag is what makes it self-invalidating: a reset and a
late-participant reassignment each mint a new draw id, so everyone reverts to "has not looked",
which is the truth, because the link they followed is the one the API now refuses as obsolete.

**Invitation status has exactly one definition, `InvitationStatusRule`.** The managed-invitation list
and the readiness nudge list read the same rows through different services. Two copies of the
"revoked → accepted → expired → delivery feedback" ladder would eventually disagree about what
"bounced" means, and bounced is the status an organizer most needs to act on.

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

**`dev-up-app.sh` and `dev-aws-setup.sh` have to agree on the env keys.** They stopped agreeing at
#365: the hosted-login migration made the pool id and the region no longer app configuration, and
`dev-aws-setup.sh` now *removes* both from an existing `app/.env.local` — while `dev-up-app.sh` kept
demanding them. The product app's dev server refused to start on every machine, with an error telling
you to re-run the setup script that had just deleted the keys. Fixed on 2026-08-28. If you add or
retire an `EXPO_PUBLIC_*`, change both files in the same commit.

**`/app/...` is a marketing-origin path, and three services were still building it.** The product
app was once served under `www.humbugg.com/app`; when it moved to `app.humbugg.com` the marketing
site kept 301ing the old shape and `APP_BASE_URL` became the app's own origin — so
`{APP_BASE_URL}/app/groups/{id}`, which `BillingService`, `ReminderService` and
`LateParticipantService` all built, resolved to `https://app.humbugg.com/app/groups/{id}`: a route
Expo Router does not have. Every Stripe checkout return, every reminder email and every
late-participant email pointed at the not-found screen. Fixed on 2026-09-02; a test now pins the
checkout return. **If you build a link to the product app, its paths are `/groups/{id}`,
`/organize/{id}`, `/join/{id}` and `/settings` — there is no `/app` prefix on that origin.**

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
