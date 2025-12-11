# Humbugg Web (React)

This directory contains the standalone Humbugg web client. It replaces the legacy ASP.NET MVC app with a modern React + Vite SPA that talks directly to the Flask backend (`../backend`) and authenticates with AWS Cognito.

## Development

```bash
cd frontend
npm install
npm run dev # opens http://localhost:5173
```

Environment variables (via `.env` or `VITE_*`) can override defaults. The build output is configured (via `vite.config.ts`) to expect the app to be hosted under `/app/` in production:

- `VITE_API_BASE_URL` – defaults to `http://localhost:5001`
- `VITE_COGNITO_DOMAIN` – defaults to `https://your-domain.auth.us-east-1.amazoncognito.com`
- `VITE_COGNITO_CLIENT_ID` – defaults to `humbugg-web`
- `VITE_COGNITO_CLIENT_SECRET` – defaults to `replace-me`

## Usage

1. Ensure your AWS Cognito user pool (and app client) plus the backend API are running. Set the environment variables above (and the backend `.env`) to match your user pool/DocumentDB connection.
2. Visit `http://localhost:5173` and sign in using the password grant form, or paste an existing bearer token issued by Cognito.
3. The dashboard fetches your profile and groups directly from the API and lets you create groups, enroll members, and trigger matches.
