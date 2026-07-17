# Humbugg infrastructure

Terraform owns Humbugg infrastructure.

- `envs/prod` owns the production Cognito pool, DynamoDB tables, Lambda/ECR,
  API Gateway, S3, CloudFront, the service-specific `humbugg.com` certificate,
  and Route53 aliases in the existing `humbugg.com` and `andreas.services` zones.
- `envs/dev` owns only the development Cognito pool used with the local API and
  DynamoDB Local.
- State is stored at `humbugg/prod/terraform.tfstate` and
  `humbugg/dev/terraform.tfstate` in the shared Terraform state bucket.

The API exposes public `GET /health` and protects `/api/*` with a Cognito JWT
authorizer. CloudFront serves all browser routes from the SPA and proxies
`/api/*` and `/health` to API Gateway.

Apply infrastructure through the GitHub workflows. Use local Terraform only
for read-only plans or when deliberately bootstrapping the development auth
environment with an authenticated AWS profile.

The CloudFront distribution serves only `https://humbugg.com` as canonical.
Viewer requests for `www.humbugg.com` or `humbugg.andreas.services` receive a
permanent `308` redirect with the original path and raw query string. Redirect
behavior is tested locally and in the PR workflow; the production workflow
also verifies both legacy hostnames after deployment.

## SES domain authentication

The `email` module repairs or creates the `humbugg.com` SES domain identity in
us-east-1 using the idempotent SES verification APIs. Terraform owns:

- the `_amazonses` identity-verification TXT record;
- three Easy DKIM CNAME records;
- `mail.humbugg.com` as the custom MAIL FROM domain, with SES MX and SPF;
- `_dmarc.humbugg.com` with an initial monitoring policy (`p=none`) and relaxed
  DKIM/SPF alignment suitable for the MAIL FROM subdomain.

Production transactional mail uses `no-reply@humbugg.com`. The deploy workflow
waits for identity, DKIM, and MAIL FROM status to reach `SUCCESS`, then exercises
delivery, bounce, and complaint feedback with SES mailbox-simulator addresses.
It never sends a test message to a real recipient. Tighten DMARC only after
deliverability monitoring is in place.

The backend Lambda has no direct SES, S3, SQS-send, or SMTP permissions. The
shared Mailer platform grants it `execute-api:Invoke` only for Humbugg's message
and attachment-registration routes. A separate least-privilege status Lambda
consumes Humbugg's Mailer status queue and updates
`humbugg-email-messages`. The table records normalized state and expires records
after 90 days.

AWS names Cognito's custom-SES mode `DEVELOPER`; it is unrelated to Humbugg's
development environment. The production Cognito pool uses that mode to send
signup and recovery messages from the Humbugg SES identity. Those messages
bypass the Mailer API, while the SES authentication configuration set sends
their delivery feedback through Mailer. The development Cognito pool retains
AWS's managed `COGNITO_DEFAULT` sender.
