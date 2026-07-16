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
