# Humbugg implementation plan

What is built, what is next, and the order it has to happen in. Written for whoever — human or
agent — picks this up next.

**Issues are the source of truth for scope; this file is the source of truth for *order*.** A
GitHub issue says what a thing is. It does not say that a purchase flow is worthless until the
capabilities it sells are reachable, or that #365 gets more expensive every week it waits. That is
what this file holds. When they disagree about scope, the issue wins and this file should be
corrected.

**A closed milestone is not evidence.** Three separate issue comments in this repo have described a
capability as delivered when only its endpoint was, and the Plus milestone currently reads zero open
while six of its capabilities have no screen. Check the caller and the screen before you believe
either.

Last reconciled against the repo on 2026-09-02.

---

## Where it stands

Live at `https://www.humbugg.com` (product app at `app.humbugg.com`, API at `api.humbugg.com`).

| Milestone | Closed | Open | State |
|---|---|---|---|
| Foundation | 13 | 0 | Complete |
| Free | 13 | 0 | **Complete.** #138 closed 2026-09-02 |
| Plus | 10 | 0 | **Complete, and now reachable.** #574 closed the gap the nine left |
| Work | 0 | 10 | Deliberately untouched |
| Launch | 3 | 10 | No longer gated — Free is complete and Plus is reachable |

### How it got out of order, and why that matters

Work jumped from Foundation straight to Plus, so the **paid tier was finished before the free one
existed**. Six PRs of Plus backend — managed invitations, scheduled reminders, co-organizers,
customization, reusable templates, post-draw late-participant reassignment — sat unmergeable for
five weeks, then merged on 2026-08-27 along with the first two pieces of Free.

Half of that is now fixed and half is not, and the difference is the single most important thing to
understand about this codebase today.

**Fixed:** the organizer surface exists (#133, at `/organize/{groupId}`) and Plus can be bought
(#141). Both landed on 2026-09-02.

**Not fixed: every Plus capability is still unreachable.** Managed invitations, scheduled reminders,
co-organizers, exchange customization, reusable templates and late-participant reassignment are all
built, tested, deployed — and rendered by no screen. `humbugg/app/src/api/client.ts` has a working
client method for each; grep the `src/` tree for any of them and you get one hit, the client itself:

```
listInvitations  createInvitations  getReminders   updateReminders
setOrganizerRole listTemplates      applyTemplate  previewLateParticipant
updateCustomization
```

So somebody can now pay $12 for six capabilities they cannot use. **That is the most urgent thing
in this file**, and it has no issue: the Plus milestone reads 0 open because every issue in it
described a backend that was in fact delivered. Opening one is step one for whoever picks this up.

Do not read the Plus milestone being closed as "Plus is done".

---

## Critical path

The four issues this section used to list — #133, #141, #130→#131→#132, #129 — are three done and
one deliberately deferred. What replaced them, in order:

### 1. Wire the Plus capabilities to a screen — **done**, as #574

Six shipped capabilities that nobody could reach. `/organize/{groupId}` was the surface they were
always meant to live on, and the wiring is now there — three PRs, one per pair.

**It was fifteen client methods with no caller, not the nine first counted.** `saveTemplate`,
`deleteTemplate` and `sendReminder` were missed on the first pass, which is worth remembering: the
gap was found by grepping for callers of `api.*`, and the same grep is the only honest way to check
it has not reopened. Every one of the fifteen has exactly one caller today.

Three things that came out of the wiring rather than the plan:

**A capability's Plus refusal must not carry its own checkout button.** The first attempt rendered
`PlusRefusalCard` on the organizer dashboard, which put two checkout buttons for one purchase on
the page; `billing.spec.ts` caught it as `getByText('$12 once, for this exchange')` matching twice.
`PlusLockedNote` names what is locked and points at the single billing panel — and tells a
co-organizer whose decision it is, since `GET .../billing/plus` is owner-only and there is no panel
to send them to.

**"Not loaded yet" and "failed to load" are different states.** Every capability panel holds its
content back until the first read lands, because an empty list and an unread one look identical.
A failed read is also "not landed", so the catch set an error and the guard under it returned null —
the panel was simply absent, error and all. That shipped once, in the invitations panel.
`PanelLoadFailure` is the third state, and every panel has it now.

**A capability with no GET is refused on save, which is too late.** Customization is a PUT only, so
a Free organizer would get a whole form that can only fail. It reads `group.plan` upfront — the
server's word carried on the group, not a re-derivation — and keeps the 402 handler underneath.

What each capability's screen owes, recorded because it is the part that is not obvious from the
endpoint: reminders must say **in one sentence** what will be sent and to whom, from the saved
settings and again from the draft; their hours are UTC and are shown as UTC, because converting
them would read as a fact while being wrong for anyone with participants elsewhere. Applying a
template **rewrites** the exchange and sends invitations, so the panel says what it replaces before
the button and ticks nobody by default. A late participant moves matches people may already have
acted on, so the count comes before the commit and a stale proposal drops back to the preview
rather than retrying a dead `proposal_id`.

### 2. #138 — mobile and assistive-technology verification — **done**

It closed Free. Three things came out of it that outlive the issue:

**The `FieldLabel` trap is now a CI check, because reasoning did not stop it.** An `aria-label` on a
control inside a `FieldLabel` is silently overridden by the design system's `aria-labelledby`, so it
reads as the working pattern and gets copied. Eighteen had accumulated, and the trap cost three
separate mistakes in one afternoon before anything counted them. `npm run a11y:check` counts them
now; removing all eighteen changed no test, which is what "silently" means.

**Two colours failed WCAG AA and nothing would have noticed.** `accent` as 14px link text was
3.77:1 and the design system's `Avatar.Fallback` paints `muted` on `surfaceAlt` at 4.13:1. Both are
fixed by ~5–10% darkenings — imperceptible as brand, decisive as ratio — in `brand-colors.json`,
the marketing site's `styles.css` and the regenerated Cognito document. `contrast.test.ts` pins
every pair the app actually paints, so the next brand edit is what runs the check.

**`/settings` had no browser coverage at all**, which is how it was the one screen nobody had
looked at narrow. It is in the mobile sweep now.

The manual remainder — a real screen reader, gestures, the largest text size, a two-account
walkthrough — is [`free-verification-checklist.md`](free-verification-checklist.md). It stayed short
because everything a machine could take was taken off it first.

---

### What the four old critical-path items left behind

Kept because the reasoning still governs the code, not because the work is outstanding.

**#133 — the readiness dashboard.** Every state is decided by the server and the app renders its
label, so "ready" cannot come to mean two things. Its gift-progress panel is filled in by #132 now;
it reports counts and never a name. One acceptance criterion is still deliberately unmet — "works
for each Work exchange" — because the wish roll-up is O(participants) queries, which is nothing at 6
or 50 and far too much at 10,000. See the Work note under "Seams".

**#141 — buying Plus.** No price is stated in the app: the amount, the currency and both participant
ceilings come from `GET /api/plans`, which reads what Stripe charges against. "Plus is active" means
the ENTITLEMENT exists, never `status: paid` — the webhook writes the entitlement and the plan in one
transaction and `HasCapability` reads the entitlement, so a paid row without one is money taken and
not yet applied. Native uses no return URL: an `https://` success URL cannot re-enter the app, so
Checkout opens in the system browser and closing it re-reads the purchase. Live Stripe mode is still
blocked (#159), so an environment whose Plus plan carries no `price_id` shows "Plus is not on sale
yet" rather than a button whose only outcome is a 409.

**#130, #131, #132 — the wishlist spine, and one privacy pattern three times.** Each stores the
sensitive fact where it cannot leak, rather than filtering it on the way out:

- A **purchase claim** lives on the claimant's own membership row, so a wishlist owner — who never
  reads another member's private membership fields — has no read path to it at all.
- A **question thread** stores no giver anywhere; a message records which SIDE wrote it and every
  request re-derives the giver from the draw. Both parties receive the byte-identical payload, so a
  leak would have to be visible in the one type they share.
- **Gift progress** is two facts owned by two people: the giver's stage on their own row, the
  recipient's "it arrived" on the giver's row, written by inverting the draw so the recipient never
  learns whose row it was.

In all three the test asserts the SCHEMA, not the endpoint — a field that does not exist cannot be
returned by an endpoint written next year. All three are draw-scoped, so a reset invalidates them
together. Claims and questions are never audited (an audit row carries actor and target, which for
either would be the assignment); gift progress is, because its rows name only the actor and a stage.

Confirmed with the maintainer on 2026-09-02: **a wishlist is visible to the assigned giver and
nobody else.** Broadening that would be a separate product change.

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

The order is in "Critical path" above. What follows is the reasoning behind work already done that
the code still depends on, plus the milestones beyond Free.

**#136 hinged on one fact about member ids.** Exclusions are keyed by member id, and a new exchange
has no members, so a literal copy would name last year's ids and constrain nobody. It works because
`MembershipRepository.MemberId` is `sha256(groupId:userId)` — *derived*, not random — so what
somebody's id will be in the new exchange is known before they join. The pairs are translated up
front and lie inert until both people are there. If that id ever becomes random, repeating loses its
exclusions and this is where to look.

Repeating deliberately invites nobody. The prior roster comes back as a list of NAMES for the
organizer to send the link to; enrolling last year's participants would put people in a draw they
never agreed to.

**#129 is the service's only outbound request, and its safety lives in one file.**
`WishUrlSafety` judges the resolved ADDRESS rather than the hostname, and it is installed as the
HTTP handler's `ConnectCallback` so the connection is made to the address that was checked — a
separate "validate then fetch" is a DNS-rebinding hole. Redirects are followed by hand so each hop
is re-inspected. The full boundary is in [`threat-model.md`](threat-model.md#outbound-requests-129);
change any of it there first.

Writing its tests found three real defects in the fetcher, one of which is worth remembering:
**on Unix, `Uri.TryCreate("/img/x.jpg", UriKind.Absolute, …)` succeeds**, producing
`file:///img/x.jpg`. A site-relative `og:image` therefore never reached the relative-resolution
branch. Nothing unsafe followed — the scheme check refused it — but "absolute" and "has a scheme we
want" are different questions and this codebase now asks the second one.

**Three times now an issue comment has described a capability as built when only its endpoint was.**
#135's said the edit endpoint existed — it did, and `api.updateGroup` was called from exactly one
place in the app, the readiness dashboard's address switch, so an exchange's name, dates and
spending limit were unchangeable through an API that had always accepted the change. #137's whole
premise was that notifications were partly delivered, and `DrawCompleted` had a template with no
caller. #134's said invitation rotation was "not implemented" — it works — while the two things
genuinely broken were not mentioned at all. **Check the caller and the screen, not the endpoint.**

**#134 is the sharpest example, because the dead code was also wrong code.**
`api.getInvitation` existed, was called by nothing, and would have failed if it had been: it fetched
a relative `/api/…` path from a time the app was served same-origin behind the marketing
distribution, and it put the invite secret in a **query string** — which API Gateway and CloudFront
both write to an access log, and which is the exact leak the URL fragment exists to prevent. The
e2e stub even had a route for the endpoint pointing at a fixture nobody had ever captured; it threw
ENOENT the first time the screen actually called it. Nothing that is never run is known to work.

**#135 carries the concurrency answer the rest of the service will want.** `PATCH /groups/{id}`
accepts the `updated_at` the client read and refuses a save that would flatten somebody else's, on
the timestamp the row already has rather than a version attribute somebody would forget to bump.
Last-write-wins is the wrong default whenever the loser is never told, which is most of the time.

**#137 turned on a capability the whole service was missing: a verified email address for any
account.** Humbugg stores none of its own, and until now the only reachable address was on an
accepted managed invitation — a Plus capability — so a Free exchange could not be notified at all.
That is why `DrawCompleted` had a template and no caller for months. `IAccountDirectory` reads a
**verified** address back from Cognito at send time; `email_verified` is the difference between an
address somebody proved they control and a string they typed, and sending to the latter would let
anyone who can sign up point Humbugg's mail at a stranger. The IAM grant is `AdminGetUser` on the
pool ARN alone: the admin API family also contains `AdminDeleteUser`, so a wildcard there would let
a compromised API delete the pool to send an email.

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
`DsField.Root`, which supplies the accessible name via `aria-labelledby` from the label text, so an
`aria-label` on the control inside is silently ignored — and a test that queries by it fails with
"unable to find an element", naming a label that is right there on screen. Fold "(optional)" into
the label string, the way `wishlist.tsx` does with "Link (optional)"; that is what the accessible
name will be. `group.tsx` and `settings.tsx` still pass ineffective `aria-label`s; harmless, but
misleading, and they are what makes this look like the working pattern.

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
