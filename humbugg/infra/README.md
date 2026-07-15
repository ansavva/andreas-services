# Humbugg infrastructure

Terraform owns Humbugg infrastructure.

- `envs/prod` owns the production Cognito pool, DynamoDB tables, Lambda/ECR,
  API Gateway, S3, CloudFront, and Route53 alias.
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
