# Humbugg

Humbugg is a public Secret Santa application at
`https://humbugg.andreas.services`. Organizers create an exchange and share a
private invitation link. Participants manage their own wish list, avoidances,
and optional mailing address. A constrained draw reveals exactly one recipient
to each participant.

## Local development

Local application data always uses DynamoDB Local. Authentication uses the
separate `humbugg-development` Cognito pool.

1. Apply `infra/envs/dev` once, either with the manual **Humbugg · Auth · Dev**
   workflow or Terraform using an authenticated AWS profile.
2. Copy `frontend/.env.local.example` to `frontend/.env.local` and fill in the
   two Terraform outputs from the development environment.
3. Export those same Cognito values for Docker Compose, then start the .NET API:

   ```bash
   cd humbugg/backend
   docker compose up --build
   ```

4. In another terminal, start the web application:

   ```bash
   cd humbugg/frontend
   npm install
   npm run dev
   ```

The frontend runs at `http://localhost:5173`, the API at
`http://localhost:5001`, and DynamoDB Local at `http://localhost:8001`.

The frontend uses React Router server rendering. Marketing HTML, page metadata,
`robots.txt`, and `sitemap.xml` are rendered by the frontend server; browser
assets are emitted separately for CloudFront and S3.

## Checks

```bash
cd humbugg/backend && dotnet test Humbugg.slnx
cd humbugg/frontend && npm ci --legacy-peer-deps && npm run typecheck && npm test && npm run build
terraform fmt -check -recursive humbugg/infra
```

Production deploys remain owned by `.github/workflows/humbugg-prod.yaml`.
