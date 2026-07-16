# Humbugg web application

React Router framework mode, React, Tailwind CSS 4, AWS Amplify Auth, and
`@ansavva/design-system` power the public marketing and authenticated customer
experience. Public routes are server-rendered for crawlable marketing content,
metadata, canonical URLs, robots, and sitemap support. Authenticated routes
hydrate into the same React application in the browser.

Copy `.env.local.example` to `.env.local`, use the development Cognito outputs,
then run `npm install && npm run dev`. Local `/api` and `/health` requests are
proxied to the .NET API at `http://127.0.0.1:5001`; production uses the same
public origin through CloudFront. `VITE_APP_BASE_URL` controls absolute metadata
URLs during a build; production always builds it as `https://humbugg.com`.

`npm run build` creates `build/server` for the SSR Lambda and `build/client`
for the S3 asset origin.

Never place a Cognito client secret or AWS credentials in frontend environment
files. The web client is intentionally secretless.
