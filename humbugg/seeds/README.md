# `seeds/` — what a seeded dev stack holds

One fixture, one loader (`scripts/dev-seed.mjs`), no code here.

| File | Says | Loaded by |
|---|---|---|
| `dev.json` | Who exists on a developer's machine — seven `.test` people — and which exchanges they are in, on which plan | `scripts/dev-aws-seed.sh`, by hand, after `dev-aws-setup.sh`, with the backend running |

**Every load converges.** Accounts are created if absent and their password set
on every run (one shared value, `HUMBUGG_DEV_USER_PASSWORD` in
`~/.config/andreas-services/humbugg/dev.env` — never in a file here). Profiles
are `PUT`. An exchange is keyed on (organizer, name), so a second run finds the
one it made; a join by an existing member is a no-op on the server; a Plus
exchange that already carries an entitlement is left alone. Rows that exist are
**left alone** even if the fixture has since changed — a seeded stack is
somewhere people work — so **a changed exchange is a new name**.

**Rows go through the API, not the tables.** The loader signs in as each person
over real SRP and makes the requests the app makes — `PUT /me`, `POST /groups`,
`POST /groups/{id}/join`, `POST /groups/{id}/billing/plus/checkout`. That is why
the backend must be up (`scripts/dev-up.sh`) and why a malformed fixture fails
with the API's own message rather than writing a row the service has stopped
agreeing with. Plus is **bought**, not granted: the loader completes the real
test-mode Checkout the backend reserves with the Stripe CLI's `tok_visa` and
waits for the webhook to come back through this machine's relay — the
`webhook-consumer` Compose service that `dev-up-backend.sh` starts with the API.
If it is not running, the event waits in the queue and the exchange flips to
Plus when it next is.

**Nothing here is real.** Every address ends in `.test` (RFC 2606 — it can never
be a mailbox, and nothing is mailed anyway: the wrapper passes
`MessageAction SUPPRESS`); every name is invented. The wrapper refuses a pool
not named for this machine, the loader refuses an API base that is not
loopback, and both refuse an address that is not `.test`. There is no staging
or prod mode and no flag that makes one.

## What the fixture is for

The two states one account and one browser cannot reach:

- **`free-full`** — the Free ceiling. Organizer plus five, exactly
  `HUMBUGG_FREE_PARTICIPANT_LIMIT` (6). Sign in as `spare@humbugg.test` and open
  the exchange's invite link (the loader prints it; or tap **Invite** as the
  organizer) to see the 402 a seventh participant gets. Sign in as the
  organizer to see the billing card say the exchange is full and offer Plus.
- **`plus-exchange`** — the same organizer's other exchange, already on Plus:
  managed email invitations, co-organizers, customization and late
  participants, with nothing bought by hand.

Plans are per **exchange**, not per person — one organizer holds both.

## Adding a person or an exchange

Edit `dev.json` and re-run `scripts/dev-aws-seed.sh`. A person is an account, a
profile and a `handle` other entries refer to; an exchange is an organizer, a
name, a plan and the participants who join it. Lower
`HUMBUGG_FREE_PARTICIPANT_LIMIT` below the fixture's roster and the loader
refuses, naming the participant that would not fit, rather than seeding an
exchange that is silently short.

The tiers that read real rows: [`docs/TESTING.md`](../docs/TESTING.md).
