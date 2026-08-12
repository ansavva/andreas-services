# Humbugg — product app (`app.humbugg.com`)

The authenticated half of Humbugg: sign-in, the dashboard, a group, settings, and
the invitation landing page. Built with **Expo + Expo Router** and exported as a
static single-page web bundle.

The marketing half lives in `humbugg/web` and the API in `humbugg/backend`.

## Why Expo, for a thing that ships as a website

The product used to be routes under `humbugg.com/app/*` in the same React Router
SSR app as the marketing site. That shape can serve a browser and nothing else.
This one is a React Native codebase that *also* runs in a browser, so an iOS and
Android build later is a `eas build` away rather than a rewrite.

The concrete mechanism is leaf resolution in `@ansavva/design-system`. Every
component there is a `.web.tsx` / `.native.tsx` pair behind one extensionless
export, and the consumer's bundler picks the leaf:

| Consumer | Bundler | Leaf |
| --- | --- | --- |
| `humbugg/web`, `website/` | Vite | `.web.tsx` — Tailwind over `theme.css` |
| this app, on a device | Metro | `.native.tsx` — RN primitives |
| this app, in a browser | Metro | `.native.tsx`, rendered by `react-native-web` |

That third row is the point, and it does not happen by default — see
[`metro.config.js`](metro.config.js), which is the whole reason that file exists.
Metro building for `web` would otherwise take the `.web` leaves, and Tailwind
class strings mean nothing in a project with no Tailwind pipeline: the app would
compile, bundle, and render unstyled.

**There is no Tailwind here.** Styling is React Native `StyleSheet`. Reaching for
a class string in this directory means you are in the wrong mental model.

## Layout

```
humbugg/app/
├── app.json            scheme: humbugg · web.bundler: metro · web.output: single
├── metro.config.js     the native-leaf resolver described above
├── jest-setup.ts       native-module mocks
└── src/
    ├── amplify.ts      Amplify's RN wiring — imported FIRST in the root layout
    ├── app/            Expo Router routes ONLY. Nothing else belongs here.
    ├── api/            the API client, ported from the web app
    ├── components/     shared UI, composed from the design system
    ├── config/         policies + the marketing-site origin
    ├── context/        auth and profile providers
    ├── screens/        screen bodies; each route file just renders one
    ├── theme/          the brand — see below
    └── utils/          validation, avatars, the invite fragment, session storage
```

## Routes

Paths are relative to `app.humbugg.com`. `(auth)` and `(protected)` are route
**groups** — they add no path segment, they only decide what shares a layout.

| File | Path | Was |
| --- | --- | --- |
| `src/app/(auth)/login.tsx` | `/login` | `/login` |
| `src/app/(auth)/signup.tsx` | `/signup` | `/signup` |
| `src/app/(auth)/confirm.tsx` | `/confirm` | `/confirm` |
| `src/app/(auth)/forgot-password.tsx` | `/forgot-password` | `/forgot-password` |
| `src/app/join/[groupId].tsx` | `/join/:groupId` | `/join/:groupId` |
| `src/app/(protected)/index.tsx` | `/` | `/app` |
| `src/app/(protected)/groups/[groupId].tsx` | `/groups/:id` | `/app/groups/:id` |
| `src/app/(protected)/settings.tsx` | `/settings` | `/app/settings` |

`src/app/(protected)/_layout.tsx` is the redirect guard that replaced the web
app's `<ProtectedRoute>` wrapper. `/join/:groupId` sits deliberately outside it:
an invited person arrives signed out.

### The invite secret is in the URL fragment

The backend mints `{APP_BASE_URL}/join/{groupId}#invite={secret}`. A fragment is
never sent to a server, never logged, and never leaks through a `Referer` — which
also means no router can hand it to us. `src/utils/invite.ts` reads it from
`location.hash` on web and from the deep link on native, and stashes it
immediately, because signing in navigates away and the fragment does not follow.
`src/utils/invite.test.ts` guards that parsing: an invitation already sitting in
someone's inbox cannot be reissued.

## The brand

Humbugg's appearance lives in two places on the web side, and only one of them
ports itself.

**Semantic roles → `src/theme/theme.ts`.** One `ThemeProvider` at the root of
`src/app/_layout.tsx`, carrying the values from `humbugg/frontend/src/styles.css`'s
`@theme` block. Two traps are handled there and documented in the file:

- On native the derived states are **pre-computed, not live blends**. Overriding
  `primary` does not move `primaryHover` / `primaryActive` the way `color-mix()`
  does on web, so Humbugg's `#17483a` / `#113b30` are set explicitly.
- `ThemeOverrides` is a loose `Record`, so a **misspelled role key is silently
  ignored** — you get a default-coloured component, not an error.

**Bespoke CSS → `src/theme/styles.ts`.** `.hero-card`, `.avatar-chip`,
`.eyebrow`, `.status-pill` and the Tailwind utilities from the old page
components, re-stated once as `StyleSheet` objects with the same radii, spacing,
weights and shadows. Put new ones there rather than inlining literals.

**Fonts are a real step, not a token.** Spectral, Archivo and Lily Script One are
loaded through `expo-font` in the root layout; React Native resolves one
registered family name per style, so each weight is its own registration. Import
them **per weight** (`@expo-google-fonts/archivo/400Regular`) — the family root
re-exports all eighteen and Metro follows the whole barrel into the bundle.

Never hard-code a colour a semantic role covers. → the `design-system-ui` skill.

## Local development

```bash
cp .env.example .env.local     # or let humbugg/scripts/dev-aws-setup.sh write it
npm install                    # needs NODE_AUTH_TOKEN, see below
npm run web                    # http://localhost:8081
npm run ios                    # or android, for a device/simulator
```

`@ansavva/design-system` and `@ansavva/tokens` are on GitHub Packages, which
needs a `read:packages` token for **every** read — there is no anonymous install.
The committed `.npmrc` reads `${NODE_AUTH_TOKEN}`; get one with:

```bash
eval "$(../../scripts/github-packages-auth.sh --export)"
```

A `401`/`404` on the `@ansavva` scope almost always means unauthenticated rather
than missing.

Both packages are `0.x`, where npm's caret rule is narrower than most people
expect: `^0.14.1` means `>=0.14.1 <0.15.0`, so a minor release does not reach you
until you widen the range yourself. Read
`node_modules/@ansavva/design-system/CHANGELOG.md` before widening.

## Environment variables

Everything is inlined at build time, so `EXPO_PUBLIC_*` is correct — none of it
is a secret. A static export has no server, which is why the Cognito ids that
used to come from the SSR `loader` are baked in here instead.

| Variable | Purpose | Production |
| --- | --- | --- |
| `EXPO_PUBLIC_API_BASE_URL` | the API's own origin | `https://api.humbugg.com/api` |
| `EXPO_PUBLIC_COGNITO_USER_POOL_ID` | user pool | — |
| `EXPO_PUBLIC_COGNITO_CLIENT_ID` | app client | — |
| `EXPO_PUBLIC_AWS_REGION` | region | `us-east-1` |
| `EXPO_PUBLIC_WEB_BASE_URL` | marketing site, for the legal links | `https://www.humbugg.com` |

With no user pool configured the app settles into "signed out" rather than
hanging on a session fetch that can only fail, so a bare checkout still runs.

## Checks

```bash
npx tsc --noEmit          # needs moduleSuffixes — see tsconfig.json
npm test                  # jest-expo + @testing-library/react-native
npx expo export -p web    # → dist/, a single-page bundle
```

`tsconfig.json` sets `moduleSuffixes: [".native", ""]` for the same reason
`metro.config.js` exists: tsc has no notion of a platform, so without it every
design-system import fails to resolve.

To prove the leaf split is real, export with source maps and check what came in:

```bash
npx expo export -p web --source-maps
# every @ansavva/design-system source should be *.native.tsx, and
# react-native-web should be present. A .web.tsx in that list is a regression.
```

## Deployment

Nothing here deploys on its own yet. The S3 + CloudFront hosting, the workflow
jobs, and the DNS cutover to `app.humbugg.com` all arrive with the hosting split.
The export it expects is `web.output: "single"` — one `index.html`, with the
distribution mapping 403 **and** 404 to it at status 200 so deep links like
`/join/abc` and `/groups/xyz` reach the router instead of the bucket.
