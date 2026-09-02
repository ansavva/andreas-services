# Humbugg Stripe Setup & Runbook (Test Mode)

This runbook establishes a **test-mode-only** billing foundation for Humbugg. It
covers creating the Stripe test account, creating the Plus and Work test
products/prices, where every ID and secret is stored, the rotation procedure,
ownership, and the gate that keeps live mode disabled.

> **Live mode is BLOCKED.** Real payments are not accepted. Live-mode activation
> is gated behind the merchant-identity / legal-entity review tracked in
> **issue #159**. The backend refuses any live-mode key or `HUMBUGG_STRIPE_MODE=live`
> at startup, and the Terraform billing module only ever stores test-mode values.

Issue **#123** established the configuration surface and secure wiring. Issue
**#139** adds Checkout Session creation, signature-verified webhook processing,
the idempotent payment ledger, and per-exchange Plus entitlement writes.

---

## 1. Create the Stripe test account

> TODO (owner action — cannot be automated in this repo): a human with the
> Humbugg billing owner account must perform these steps in the Stripe Dashboard.

1. Create (or reuse) the Humbugg Stripe account. Keep the account toggle in
   **Test mode** (top-right of the Dashboard) for every step below.
2. Do **not** submit business/merchant-identity details yet — that is part of
   issue #159 and would begin live-mode activation, which is out of scope.
3. No real bank account or card is required to operate in test mode.

## 2. Create the test products and prices

Create two products with a single price each. The amounts mirror the backend
plan defaults (`HUMBUGG_PLUS_PRICE_CENTS=1200`, `HUMBUGG_WORK_PRICE_CENTS=9900`).

| Product | Price | Billing | Resulting IDs |
|---|---|---|---|
| **Humbugg Plus** | $12.00 USD | One-time | `prod_...` (Plus product), `price_...` (Plus price) |
| **Humbugg Work** | $99.00 USD / year | Recurring (annual) | `prod_...` (Work product), `price_...` (Work price) |

> TODO (owner action): create these in **Test mode** and copy the four IDs. All
> four are **test-mode** IDs (`prod_...` / `price_...`, from a test account).

For Plus, the repository provides an idempotent provisioning command. After
authenticating the Stripe CLI against the Humbugg test account, run:

```bash
./humbugg/scripts/configure-stripe-plus-test.sh
```

It reuses a tagged Plus product and active `$12 USD` one-time price when they
already exist, creates only missing resources, verifies the resulting price,
and prints the two GitHub environment variable assignments. It never accepts
or stores a secret key.

### Register the production test webhook

In the Stripe Dashboard while **Viewing test data**, create an endpoint for:

```text
https://humbugg.com/api/billing/stripe/webhook
```

Subscribe only to:

- `checkout.session.completed`
- `checkout.session.async_payment_succeeded`
- `checkout.session.async_payment_failed`
- `checkout.session.expired`
- `charge.succeeded`
- `charge.refunded`

Copy that endpoint's `whsec_...` value into the GitHub environment secret
`HUMBUGG_STRIPE_WEBHOOK_SECRET`. This is separate from the temporary signing
secret printed by `stripe listen` for localhost.

Product and price IDs are **configuration, not code** — the backend
`PlanCatalog` reads them from environment variables (see the mapping below), and
`StripeSettings` reads the keys. Nothing is hardcoded.

## 3. Where each value lives

Everything flows from the `humbugg-production` GitHub Actions environment. The
deploy workflow (`.github/workflows/humbugg-prod.yaml`) injects them; nothing is
committed to the repo.

### Secrets — GitHub environment **secrets** → SSM (SecureString) + Lambda env

| Value | GitHub secret | SSM parameter (Terraform-managed) | Lambda env var |
|---|---|---|---|
| Secret key (`sk_test_...`) | `HUMBUGG_STRIPE_SECRET_KEY` | `/humbugg/prod/stripe/secret-key` (SecureString) | `HUMBUGG_STRIPE_SECRET_KEY` |
| Webhook signing secret (`whsec_...`) | `HUMBUGG_STRIPE_WEBHOOK_SECRET` | `/humbugg/prod/stripe/webhook-secret` (SecureString) | `HUMBUGG_STRIPE_WEBHOOK_SECRET` |

The `billing` Terraform module (`humbugg/infra/modules/billing`) declares these
SSM parameters. Values arrive via `TF_VAR_stripe_secret_key` /
`TF_VAR_stripe_webhook_secret` in the `deploy-infra` job. Until the secrets are
set the parameters are **not created** (the module uses `count`), so the stack
stays deployable before the Stripe account exists.

### Non-secret config — GitHub environment **vars** → Lambda env

| Value | GitHub var | Lambda env var |
|---|---|---|
| Mode (`test` / `disabled`) | `HUMBUGG_STRIPE_MODE` | `HUMBUGG_STRIPE_MODE` |
| Publishable key (`pk_test_...`) | `HUMBUGG_STRIPE_PUBLISHABLE_KEY` | `HUMBUGG_STRIPE_PUBLISHABLE_KEY` |
| Plus product ID | `HUMBUGG_PLUS_PRODUCT_ID` | `HUMBUGG_PLUS_PRODUCT_ID` |
| Plus price ID | `HUMBUGG_PLUS_PRICE_ID` | `HUMBUGG_PLUS_PRICE_ID` |
| Work product ID | `HUMBUGG_WORK_PRODUCT_ID` | `HUMBUGG_WORK_PRODUCT_ID` |
| Work price ID | `HUMBUGG_WORK_PRICE_ID` | `HUMBUGG_WORK_PRICE_ID` |

The publishable key is also mirrored into `/humbugg/prod/stripe/publishable-key`
(SSM `String`) by the billing module for discoverability.

> Leave `HUMBUGG_STRIPE_MODE` unset or `disabled` until the secrets and product
> IDs are all provisioned. Setting it to `test` without the required credentials
> makes the backend **fail fast at startup** — that is intentional.

## 4. Local development (test mode + fixtures)

No live key, real card, or payment method is ever required.

1. Copy `humbugg/backend/.env.sample` to your local env file.
2. To run **without** Stripe, keep `HUMBUGG_STRIPE_MODE=disabled` (default).
3. To exercise billing locally, install the [Stripe CLI](https://stripe.com/docs/stripe-cli):
   ```bash
   stripe login                       # test-mode account
   ./humbugg/scripts/dev-up-stripe.sh
   ```
   `stripe listen` prints a `whsec_...` webhook signing secret. Put the test-mode
   values into your env file:
   ```
   HUMBUGG_STRIPE_MODE=test
   HUMBUGG_STRIPE_PUBLISHABLE_KEY=pk_test_...   # from Dashboard (test mode)
   HUMBUGG_STRIPE_SECRET_KEY=sk_test_...        # from Dashboard (test mode)
   HUMBUGG_STRIPE_WEBHOOK_SECRET=whsec_...       # from `stripe listen`
   ```
4. Use Stripe's [test cards](https://stripe.com/docs/testing) (e.g. `4242 4242 4242 4242`)
   and `stripe trigger` fixtures for events. The backend's `StripeSettings`
   validation rejects any `sk_live_` / `pk_live_` / `rk_live_` credential, so a
   live key cannot be used by accident.

Both Checkout return URLs are `{APP_BASE_URL}/organize/<group-id>?checkout=…` — the
organizer's billing area in the product app. Locally that is
`http://localhost:8081/organize/<group-id>`, and Stripe permits HTTP only for localhost
testing, so `APP_BASE_URL` must name the **app** origin (`:8081`), not the marketing
site. The path used to be `/app/groups/<id>`, which dates from the app being served under
`www.humbugg.com/app`: only the marketing origin still 301s that shape, so once
`APP_BASE_URL` became `app.humbugg.com` every paid return landed on the not-found screen.

The billing area polls the signed-in purchase status after a successful return and waits
for the **entitlement**, not for `status: paid`. The webhook writes the entitlement and the
group's plan in one transaction and `PlanCatalog.HasCapability` reads the entitlement, so a
paid row without one is a purchase Stripe has taken money for and Humbugg has not applied —
the screen says exactly that instead of promising a capability the next request would 402.

On native there is no return URL at all: an `https://` success URL cannot re-enter the app,
so Checkout is opened in the system browser and closing it is the signal to re-read the
purchase. The API is the source of truth on both platforms; the `?checkout=` query is only
a hint about what Stripe told the browser.

## 5. Rotation procedure

Rotate on a schedule and immediately on any suspected exposure.

1. **Secret key** — in the Stripe Dashboard (test mode) → Developers → API keys →
   *Roll* the secret key. Update the GitHub secret `HUMBUGG_STRIPE_SECRET_KEY`,
   then re-run the `humbugg-prod` deploy (`workflow_dispatch`, `run_infra=true`)
   so Terraform rewrites `/humbugg/prod/stripe/secret-key` and `update-lambda`
   refreshes the Lambda env. Revoke the old key once the deploy is green.
2. **Webhook secret** — roll the endpoint's signing secret in the Dashboard,
   update `HUMBUGG_STRIPE_WEBHOOK_SECRET`, and redeploy as above.
3. **Publishable key** — rarely rotated (not secret); update
   `HUMBUGG_STRIPE_PUBLISHABLE_KEY` var and redeploy if it changes.
4. Never edit the SSM SecureString values by hand — always go through GitHub
   secrets + the deploy pipeline to avoid IaC drift.

## 6. Ownership

- **Billing / Stripe account owner:** the repo owner — owns the Stripe account,
  product catalog, and key rotation. The address is in the Stripe dashboard and
  is deliberately not recorded here; this repo is public.
- **Infra / secret wiring:** whoever owns the `humbugg-production` GitHub
  environment and the Humbugg Terraform state.
- Changes to products, prices, or keys must be reflected in the GitHub
  environment values above — not in application code.

## 7. Live-mode gate (do not remove)

Live mode stays disabled until issue **#159** (merchant-identity / legal-entity
review) is complete and explicitly signed off. Enforcement points:

- `StripeSettings.ParseMode` throws on `HUMBUGG_STRIPE_MODE=live`.
- `StripeSettings.Validate` throws on any `sk_live_` / `pk_live_` / `rk_live_`
  credential, in every mode.
- The Terraform `billing` module only ever stores the test-mode values passed in.

Activating live mode is a deliberate, reviewed follow-up — not a config toggle.
