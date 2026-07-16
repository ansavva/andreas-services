# Humbugg API

ASP.NET Core 10 API for Humbugg. Cognito owns registration and authentication;
the API accepts only Cognito access tokens for the configured secretless client.
Profiles, groups, memberships, private draws, and reveal audit events are stored
in DynamoDB.

Run from `humbugg/backend`:

```sh
dotnet test Humbugg.slnx
docker compose up --build
```

The containerized local API is available at `http://localhost:5001` and creates
the required tables in DynamoDB Local. It never connects to production tables.

## Plan configuration

`GET /api/plans` returns the authoritative Free, Plus, and Work contract used by
the backend. New and legacy groups default to Free. Each group stores its plan,
while participant limits and prices are read from environment configuration:

| Variable | Default |
|---|---:|
| `HUMBUGG_FREE_PARTICIPANT_LIMIT` | `6` |
| `HUMBUGG_PLUS_PARTICIPANT_LIMIT` | `50` |
| `HUMBUGG_WORK_PARTICIPANT_LIMIT` | `10000` |
| `HUMBUGG_PLUS_PRICE_CENTS` | `1200` |
| `HUMBUGG_WORK_PRICE_CENTS` | `9900` |

Stripe product and price identifiers use `HUMBUGG_PLUS_PRODUCT_ID`,
`HUMBUGG_PLUS_PRICE_ID`, `HUMBUGG_WORK_PRODUCT_ID`, and
`HUMBUGG_WORK_PRICE_ID`. They remain empty until test-mode billing is prepared.
Production values are GitHub environment variables injected into the Lambda;
changing them requires a targeted app redeploy, not an application code change.

## Transactional email

Application code depends on `ITransactionalEmailService` and
`ITransactionalEmailTemplates`; it never calls the AWS SDK directly. The five
typed templates cover invitations, reminders, completed draws, assignment
availability, and account-relevant exchange events. Every template produces
accessible HTML and a complete plain-text alternative with no marketing copy.

Callers provide a durable event ID. The template combines that event ID with
the category and recipient to produce a stable application message ID. Before
sending, the service conditionally reserves that ID in
`humbugg-email-messages`; repeated or concurrent delivery attempts are skipped,
while a provider failure can be retried with the same ID. SES also receives the
application message ID and category as message tags.
The ledger stores no recipient address or message body.

`HUMBUGG_EMAIL_PROVIDER` defaults to `capture`, so local runs and unit tests
record messages in memory without making network calls. Production sets it to
`ses`, uses `no-reply@humbugg.com`, and obtains AWS credentials solely from the
Lambda execution role.
