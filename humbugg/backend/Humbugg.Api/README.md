# Humbugg API

ASP.NET Core 10 API for Humbugg. Cognito owns registration and authentication;
the API accepts only Cognito access tokens for the configured secretless client.
Profiles, groups, memberships, private draws, and reveal audit events are stored
in DynamoDB.

Start the shared local Mailer and Mailpit first:

```sh
cd mailer
docker compose up --build
```

Then run from `humbugg/backend`:

```sh
dotnet test Humbugg.slnx
docker compose up --build
```

The containerized local API is available at `http://localhost:5001` and creates
the per-machine tables provisioned in AWS DynamoDB. Product email goes to Mailer at
`http://host.docker.internal:8026` and appears only in Mailpit at
`http://localhost:8025`; Mailpit has no outbound relay. The local stack never
connects to production tables.

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
submission, the service conditionally reserves that ID in
`humbugg-email-messages`; repeated or concurrent delivery attempts are skipped,
while an admission failure can be retried with the same ID. Mailer owns durable
queueing, SES delivery, suppression, and feedback. A dedicated status Lambda
records normalized outcomes in the same table with 90-day expiry. The ledger
stores no recipient address, subject, or message body.

Unit tests retain the in-memory capture adapter. The running local app uses the
unsigned Mailer API and Mailpit; production signs the same HTTP routes with the
backend Lambda role's temporary AWS credentials. Humbugg never receives S3,
SQS-send, SMTP, Mailpit, or direct SES permissions.

The email feature follows the same responsibility-based layout as Mailer:

```text
Services/
└── Email/
    ├── Core/             # messages, templates, service, and ports
    ├── Adapters/
    │   ├── Aws/          # SigV4 and DynamoDB implementations
    │   ├── Http/         # shared Mailer API client and transport
    │   └── Memory/       # unit-test capture and idempotency
    └── StatusProcessing/
        └── EmailStatusHandler.cs

Consumers/
├── ConsumerHost.cs       # registry and runtime selection for every consumer
└── EmailStatus/
    └── AwsLambdaEmailStatusConsumer.cs
```

Folders describe architectural roles, not deployment environments.
`ConsumerHost` is the single discovery and wiring point for background
consumers. A future consumer gets its own directory under `Consumers/` and one
registration in that host; `Program.cs` contains no consumer-specific branches.
For ordinary API requests, runtime composition selects unsigned Mailer HTTP
locally and SigV4 in AWS.
