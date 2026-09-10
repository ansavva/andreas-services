# Launch evidence — payments, limits, email (#160)

The automated half of #160: one row per scenario, each citing a test that exists in the repo and
that was run for this document, or a command that was run with its observed outcome. Free and Plus
only — Work is deferred (#638).

Every citation below was executed on 2026-09-09 against this machine's dev stack (`humbugg-dev-afd9fe3915fd-*`
tables, Stripe test account `acct_1TtdwZK4tW5AWYog`) unless the row says otherwise. Run summaries are
in the PR body for #160, not repeated here.

Rows the current tests genuinely cannot reach — a real browser purchase, DNS records, a real
inbox — are **not** faked here. They are [Operator rows](#operator-rows), below the table, with exact
steps and the expected observation.

## Billing (Plus, one-time $12)

| Scenario | Tier | Test or command | Result (date) | Notes |
|---|---|---|---|---|
| Checkout session creation, owner | Live command | `POST /api/groups/{id}/billing/plus/checkout` against `dotnet run` on `:5002`, real test-mode secret key from `backend/.env` | 200, 2026-09-09 | Created a real Stripe test-mode Checkout Session `cs_test_a1C5jtEHUDt6kypq3jFE0S3vQqEsFkr6nHQHg3kUr39nysGbrO3Qfsrs8g`; opened the `checkout_url` in a browser and confirmed the page: "Humbugg Plus — $12.00". Group, profile and billing rows deleted afterward. |
| Checkout refusal, non-owner and group already on Plus | Unit | `Humbugg.Api.Tests.BillingServiceTests.CheckoutRejectsNonOwnerAndExistingEntitlement` | pass, 2026-09-09 | One test, both refusals: a non-owner gets `forbidden`; an already-Plus group gets `conflict`. |
| `checkout.session.completed` writes payment + entitlement + plan atomically | Integration (Data) | `Humbugg.Api.IntegrationTests.Data.BillingRepositoryTests.A_paid_event_upgrades_the_group_and_is_idempotent_by_event_id` | pass, 2026-09-09 | One `TransactWriteItems` call against real dev-stack DynamoDB. Asserts `group.Plan == Plus` and `group.EntitlementId == "plus:{groupId}"` land in the same transaction as the payment row's `status: paid` — the ["entitlement, never `status: paid`"](implementation-plan.md) rule, read off the actual write rather than the description of it. |
| `async_payment_succeeded` / `async_payment_failed` | Unit (new) | `Humbugg.Api.Tests.StripeGatewayEventMappingTests.AsyncPaymentSucceededMapsToPaid`, `.AsyncPaymentFailedMapsToFailedRegardlessOfSessionPaymentStatus` | pass, 2026-09-09 | Real HMAC-SHA256-signed payloads through `StripeGateway.ParseWebhook` — the same verification path production traffic runs. Added because only `checkout.session.completed` had a mapping test before this PR. |
| `checkout.session.expired` | Unit (new) | `StripeGatewayEventMappingTests.CheckoutSessionExpiredMapsToExpired` | pass, 2026-09-09 | |
| A webhook that arrives late | Integration (Data, new) | `BillingRepositoryTests.A_late_paid_event_still_applies_the_entitlement_after_the_group_has_filled_its_free_cap` | pass, 2026-09-09 | Fills a Free group to its 6-participant cap directly (the roster it would actually be at if a 7th join had already been refused while the purchase sat pending), then applies the paid event. `BillingRepository.ApplyEventAsync` never reads the roster, so the entitlement lands regardless — the group is simply unblocked for participant 7 onward the moment the transaction commits. There is no time-based expiry on a reserved purchase. |
| The same webhook delivered twice | Integration (Data) + live command | `BillingRepositoryTests.A_paid_event_upgrades_the_group_and_is_idempotent_by_event_id` (second `ApplyEventAsync` call on the same event id returns `false`, one payment row); `stripe events resend evt_1UDtfqK4tW5AWYogHJGahK8S --confirm` | pass, 2026-09-09 | The repository test proves the business-logic idempotency (an `event#{id}` row makes the redelivery a recognized duplicate before any group/payment write is attempted). The resend proves the same at the wire level: Stripe redelivered the identical event id to `:5002` through `stripe listen`, and the endpoint answered `400` both times, for the same reason, with no different side effect. |
| `charge.refunded` — entitlement removed or kept? | Integration (Data, new) + Unit (new) | `BillingRepositoryTests.A_fully_refunded_charge_removes_the_entitlement_and_reverts_the_plan`; `StripeGatewayEventMappingTests.FullyRefundedChargeMapsToRefunded`, `.PartiallyRefundedChargeStaysMappedAsPaid` | pass, 2026-09-09 | **What the code does, and it is the right call:** a *fully* refunded charge removes the entitlement and reverts the group to `Free` (`BillingRepository.ApplyEventAsync`, the `nextStatus == Refunded` branch). A *partial* refund is recorded but leaves Plus active — Stripe emits `charge.refunded` for partial refunds too, and Humbugg only revokes once Stripe has given all the money back (comment on `StripeGateway.FromCharge`). |
| Invalid signature → 400 | Unit + Integration (Http, new) + live command | `Humbugg.Api.Tests.BillingServiceTests.StripeGatewayVerifiesSignatureAndMapsPaidSession` (existing); `Humbugg.Api.IntegrationTests.Http.BillingWebhookHttpTests.A_request_with_no_Stripe_Signature_header_is_refused`, `.A_request_with_an_invalid_signature_is_refused_before_any_Stripe_parsing` | pass, 2026-09-09 | Also observed live: `stripe trigger checkout.session.completed` (with `--override` metadata pointed at a real reservation) fired two genuinely-signed Stripe events — `evt_3UDtfpK4tW5AWYog0SGmzUb7` (`charge.succeeded`) and `evt_1UDtfqK4tW5AWYogHJGahK8S` (`checkout.session.completed`) — at `:5002`. Both passed real signature verification and were still refused `400`, because `stripe trigger` builds its own Stripe-priced fixture object ($30, `environment: local` unmatched) that cannot be forced to match a Humbugg reservation's amount. This is correct, defensive behavior, not a workaround failure — see the note below the table. |
| Receipt/invoice link is Stripe-hosted | Code citation | — | — | `humbugg/app/src/components/plus.tsx`, `PaidSummary`: `status?.receipt_url` opens via `Linking.openURL` under the label "View your Stripe receipt". The backend never re-hosts it — `PlusPurchaseStatus.ReceiptUrl` is `Charge.ReceiptUrl` straight from Stripe (`BillingService.GetPlusStatusAsync`). |

**Why `stripe trigger` could not produce a matching `checkout.session.completed`/`charge.refunded` pair end-to-end.** `stripe trigger` calls Stripe's real API to create its *own* product, price, and Checkout Session for each run — a fresh `cs_test_...` id at a fixture-chosen amount ($30) — then fires the resulting real, signed webhook. Overriding the metadata (`--override checkout_session:metadata.*`) worked and is what produced the two real event ids above; overriding the amount did not (`stripe trigger ... --override price:unit_amount=1200` fails the trigger itself with `checkout_amount_mismatch`, because a later fixture step has the original $30 baked in). There is no CLI path to complete a *pre-existing* Checkout Session non-interactively — Stripe's hosted Checkout page requires a browser, and this environment's data-entry policy would not let an agent fill a payment form even with a test card. The owner-checkout-creation row above used the real endpoint and a real Stripe session; completing it is the first [operator row](#operator-rows).

## Limits

| Scenario | Tier | Test or command | Result (date) | Notes |
|---|---|---|---|---|
| Free: 6 ok, 7th refused 402 naming Plus | Unit + Integration (Http, new) | `Humbugg.Api.Tests.PlanCatalogTests.FreeAllowsSixTotalIncludingOrganizer`, `.ParticipantSevenRequiresActivePlusEntitlement`; `Humbugg.Api.IntegrationTests.Http.ParticipantLimitHttpTests.Free_seats_six_and_refuses_a_seventh_with_402_naming_Plus` | pass, 2026-09-09 | The HTTP test is new — only the pure-logic (`PlanCatalog`) unit test existed before this PR. It joins through the real `POST /api/groups/{id}/join` route: owner + 5 joins fill the 6 seats, the 7th person gets `402 plus_required` naming Plus. |
| Plus: 50 ok, 51st refused, names Work | Unit + Integration (Http, new) | `PlanCatalogTests.PlusAllowsFiftyAndRejectsFiftyOneWithWorkExplanation`; `ParticipantLimitHttpTests.Plus_seats_fifty_and_refuses_a_fifty_first_pointing_to_Work` | pass, 2026-09-09 | The HTTP test seeds 49 members directly against `GroupRepository`/`MembershipRepository` (real 49 HTTP joins would just re-run the Free test 49 times) on a group written with `Plan: Plus`, `EntitlementId: "plus:{id}"`. The 50th join succeeds; the 51st gets `409 conflict` naming Work and "51". |

## Email

| Scenario | Tier | Test or command | Result (date) | Notes |
|---|---|---|---|---|
| Invitations | Unit | `Humbugg.Api.Tests.InvitationServiceTests.InitialWritePersistsDeliveryMetadata`; `Humbugg.Api.Tests.MailerIntegrationTests.UnsignedClientSubmitsTheVersionedHumbuggContract` | pass, 2026-09-09 | The second test asserts the actual wire contract Mailer receives: `/v1/services/humbugg/messages`, `category: invitation`, `message_class: exchange`, no `Authorization` header (unsigned local transport), no `service_id`/`from_address` leaked into the body. |
| Reminders | Unit | `Humbugg.Api.Tests.ReminderScheduleTests` (send-window, eligibility-before-cooldown, no Plus roster cap on automatic sends); `Humbugg.Api.Tests.ReminderAuthorizationTests` (only organizers/co-organizers may read or configure) | pass, 2026-09-09 | |
| Draw-completed | Unit | `Humbugg.Api.Tests.GroupServiceSecurityTests.ADrawTellsEveryParticipantWithAVerifiedAddress`, `.AnUnreachableParticipantDoesNotStopTheOthersBeingTold` | pass, 2026-09-09 | Confirms every participant with a verified Cognito email is sent `EmailCategory.DrawCompleted`, and one unreachable account does not stop the other 49 from being told (#137). |
| Authentication mail (sign-up, resend-confirmation, forgot-password) | Not Humbugg's code | — | — | Originates in Cognito directly (`DEVELOPER` custom-SES mode against `no-reply@humbugg.com`), never passes through this service or the Mailer API (`docs/email-operations.md`, "Cognito"). No Humbugg-owned test exercises Cognito's own mail; the SES feedback loop that authentication mail shares with product mail is what the prod smoke job below verifies. |
| Essential vs. non-essential classification and opt-out enforcement | Unit | `Humbugg.Api.Tests.EmailPreferenceTests` (classification table, opt-out suppression, fail-open when no account); `Humbugg.Api.Tests.EmailArchitectureTests` (Core has no dependency on Adapters or AWS); `Humbugg.Api.Tests.TransactionalEmailTests` (idempotent send, retry, escaped template values) | pass, 2026-09-09 | |
| Prod job `email-feedback-smoke-test` | Prod smoke (CI, not run for this PR) | `.github/workflows/humbugg-prod.yaml`, job `email-feedback-smoke-test` | — | Runs after every prod deploy, against real AWS. Sends three real messages through the SES mailbox simulator (`success@`/`bounce@`/`complaint@simulator.amazonses.com`) over the shared auth configuration set, then polls `humbugg-prod-email-messages` (60 × 10s) for `status` to reach `delivery`, `bounce`, and `complaint` respectively. What it proves that nothing local can: the deployed Lambda's SES identity, the shared configuration set, Mailer's feedback Lambda, and Humbugg's own `email-status` consumer, chained together for real. |
| Suppressed recipients are not retried | Code citation + Python unit (mailer) | `mailer/src/mailer/entrypoints/sender_lambda.py::_suppressed` (checked before every send, against `mailer-prod-suppressions`, keyed by `recipient_hash`; a suppressed address is marked `"suppressed"` and never reaches SES); `mailer/src/mailer/entrypoints/feedback_lambda.py::_suppresses_recipient` / `_suppress` (a `complaint`, or a `Permanent` bounce, adds the address — a `Transient` bounce does not); test `mailer/tests/test_feedback.py::test_only_permanent_bounces_and_complaints_suppress` | pass, 2026-09-09 (`uv run pytest tests/test_feedback.py`, 5 passed) | Suppression is enforced entirely inside Mailer, at send time — a suppressed recipient's message is never attempted, so there is nothing on Humbugg's side to "not retry." Humbugg's own `EmailStatusHandler` (`Services/Email/StatusProcessing/EmailStatusHandler.cs`) only *records* a `bounce`/`complaint`/`suppressed` status on `humbugg-prod-email-messages` for visibility — it never re-sends or re-queues. No dedicated unit test in `mailer/tests` exercises `sender_lambda._suppressed` itself (only the classification half, `_suppresses_recipient`, is tested); worth a follow-up, out of scope here — see the PR body. |

## Secrets in logs

| Scenario | Tier | Test or command | Result (date) | Notes |
|---|---|---|---|---|
| Analytics can't carry private data | Unit + doc | `Humbugg.Api.Tests.ProductAnalyticsTests` (`SanitizeDropsEveryProhibitedField` × 11 keys, `SanitizeDropsUnknownKeysNotOnTheAllowList`, `SanitizeDropsSecretLookingValuesEvenUnderAllowListedKeys`); `docs/analytics.md` | pass, 2026-09-09 | `AnalyticsDimensions.Sanitize` is two-sided: an allow-list (only `participant_count`, `member_count`, `ready_count`, `exclusion_count`, `is_repeat`, `plan_from`, `plan_to`, `billing_cadence`, `days_to_draw` survive) plus a secret/token-entropy detector that drops even an allow-listed key if its *value* looks like a token. |
| Backend logging doesn't interpolate a token, address, or card value | Grep + manual read | `grep -rn "LogInformation\|LogWarning\|LogError\|LogDebug\|LogCritical" humbugg/backend/Humbugg.Api --include="*.cs"` (excluding `obj/`, `bin/`) | clean, 2026-09-09 | 17 call sites, all read individually. None interpolates an email address, a mailing address, card data, or a Stripe/Cognito token. What they do log: account/group/message/event **ids** (opaque, not addresses), enum values (`EventType`, `Category`), and exception objects passed as structured fields (never string-concatenated into the template). No defect found — see the PR body for the full list of sites read. |

## Operator rows

Not automatable from here — either they need a real browser against production, or they need to
observe something only a live domain or a real inbox can show. Run these once the automated rows
above are green, in this order, and stop at the first one you can't complete.

1. **A real Stripe test-card purchase on `www.humbugg.com`.**
   Sign in, start a Plus checkout for a real exchange, and pay with `4242 4242 4242 4242` (any
   future expiry, any CVC) — see `docs/stripe-setup.md` for the full test-card list.
   **Expect:** redirect back to `/organize/<group-id>?checkout=success...`; the billing area polls
   until the **entitlement** appears (not `status: paid`) and then shows "Plus is on for this
   exchange"; "View your Stripe receipt" opens a real Stripe-hosted receipt.

2. **DNS: SPF, DKIM, DMARC for `humbugg.com`.**
   ```bash
   dig txt humbugg.com +short          # SPF: v=spf1 ... (Amazon SES's include)
   dig txt <selector>._domainkey.humbugg.com +short   # DKIM — selector from the SES identity
   dig txt _dmarc.humbugg.com +short   # DMARC: v=DMARC1; p=...
   ```
   **Expect:** all three resolve and validate; none are missing or set to `p=none` without that
   being the deliberate current policy.

3. **`support@humbugg.com` forwarding.**
   Send a real email to `support@humbugg.com` from an external address.
   **Expect:** it arrives in the Google Workspace inbox that owns that address (`docs/support-email.md`)
   — Humbugg's own mail path is never involved, since this is inbound, not something the API sends.

4. **A `no-reply@` receipt on a real inbox.**
   Trigger a real transactional send (an invitation, or the draw-completed mail from a real,
   small exchange) to an address you control.
   **Expect:** arrives from `no-reply@humbugg.com`, names `support@humbugg.com` as where to write
   instead, and states plainly that replying to the sending address goes nowhere
   (`Humbugg.Api.Tests.TransactionalEmailTests.EverySupportedMessageNamesTheSupportInboxAndDisownsTheFromAddress`
   is the automated half of this — it checks the template text, not delivery to a real inbox).
