# Sign-in: Cognito Managed Login

Decision record for [#365](https://github.com/ansavva/andreas-services/issues/365), part of epic
[#363](https://github.com/ansavva/andreas-services/issues/363). Decided and implemented August 2026.

## The decision

**Humbugg's app moved fully to Cognito Managed Login — hosted sign-in *and* hosted sign-up.** Six
flows left this codebase: sign-in, sign-up, confirm-code, forgot-password, confirm-reset, sign-out.
The app keeps one screen, `(auth)/login.tsx`, and it is a button.

The window for deciding this cheaply was open and is now closed: the prod pool held **zero** users
when this landed, verified live. Nothing was migrated because nothing existed to migrate.

## What Managed Login does not do

**It does not replace the Cognito pool.** `humbugg/docs/implementation-plan.md` said it did; that was
wrong and is corrected. Turning on the hosted pages changes the *client* — an OAuth block,
`refresh_token_rotation`, one dropped auth flow — and adds a branding record and a domain. The pool,
its schema, its password policy and every `sub` in it are untouched. (The pool is separately
replaceable by `username_configuration`, which is a different line with its own warning on it in
`humbugg/infra/modules/auth/main.tf` — do not confuse the two.)

## The mechanism: expo-auth-session, not Amplify

Amplify offers `signInWithRedirect`, which would have been the smaller diff. It does not work here.
On React Native it needs the **`@aws-amplify/rtn-web-browser` native module**, and `humbugg/app` has
no prebuild, no dev client and no `eas.json` — so on the two runtimes this app actually has today,
Expo Go and the web export, that module cannot load. The failure is at runtime, in the sign-in call.

`expo-auth-session` works in Expo Go, on web, and in a future EAS build with no change. It brings
`expo-web-browser` (the system-browser hand-off RFC 8252 asks for), `expo-crypto` (Hermes has no
WebCrypto, so PKCE needs a native digest) and `expo-secure-store` (the keychain the tokens live in).
Amplify and its three polyfills — `aws-amplify`, `@aws-amplify/react-native`,
`react-native-get-random-values`, `react-native-url-polyfill` — are gone. `AsyncStorage` stays; it is
used by `utils/session-store.ts`, not by auth.

**PKCE is enforced in this app and nowhere else.** Cognito has no server-side "require PKCE" toggle
for a public client, so `src/auth/oauth.test.ts` asserts that the authorize URL actually carries
`response_type=code`, `code_challenge_method=S256` and a challenge. That test is the control.

## The custom scheme

Native returns to `humbugg://auth/callback`, registered as its own literal callback URL beside
`https://app.humbugg.com/auth/callback`. Cognito matches redirect URIs **exactly** — no prefixes, no
wildcards — so both strings appear verbatim in `humbugg/infra/envs/prod/main.tf`, and the dev stack
carries `http://localhost:8081/auth/callback` alongside the same scheme.

A loopback redirect (RFC 8252 §7.3) is the alternative and is not available: it needs an HTTP
listener a React Native runtime cannot bind without a native module.

**Testing caveat.** In **Expo Go on a device the `humbugg://` scheme belongs to Expo Go**, not to
this app, so the native leg of the flow cannot be exercised there — it needs a dev build.
Day-to-day verification is the web flow on `http://localhost:8081`.

## Refresh-token rotation

Enabled, with a 30-second retry grace period. It is the reason the client's `explicit_auth_flows`
lost `ALLOW_REFRESH_TOKEN_AUTH` in the same apply: **Cognito rejects that pair at apply time**, and
neither `terraform validate` nor `tflint` can see it, so the only symptom of re-adding it is a failed
deploy.

`ALLOW_USER_SRP_AUTH` stays. Not because the hosted pages need it — they do not, Managed Login talks
to the pool server-side — but because it is the last direct-auth flow left for admin and dev tooling,
including the authenticated dev-stack round trip planned in
[#373](https://github.com/ansavva/andreas-services/issues/373).

Rotation retires the old refresh token on every use, so `src/auth/oauth.ts` persists the rotated one
and refreshes **single-flight**. Two concurrent refreshes would otherwise spend the same token twice;
the grace period is the backstop, not the plan.

## Consent moved to profile setup

The policy checkbox used to sit on the signup form, get stashed in `sessionStorage`, and be replayed
onto the first profile create. The signup form is Cognito's now, and a hosted page cannot carry
Humbugg's own terms.

So the checkbox moved to the **profile-setup form** in `src/screens/dashboard.tsx` — the first screen
after sign-up that is still ours, and one no new account can get past. The gate is unchanged in
order and in effect, and the consent rides the same first `PUT /me` it always did
(`api.saveMe(..., consent)`), which the backend still records once and immutably. The
`sessionKeys.consent` stash and its "the stash was lost" fallback are both deleted — there is no
longer a gap for a value to cross.

## Domains

| Environment | Managed Login host | Why |
|---|---|---|
| prod | `auth.humbugg.com` | A name Humbugg owns, on Humbugg's own certificate. |
| dev (per machine) | `<resource-prefix>.auth.<region>.amazoncognito.com` | A default Cognito domain. |

Dev stacks take the default because a custom one costs a certificate SAN, a hosted-zone record and a
~15-minute apply **per machine**, for pages only that machine's developer ever loads. The prefix must
be globally unique across AWS, which the per-machine id already guarantees.

`auth.humbugg.com` was added as a SAN to the existing certificate, which **replaces** it.
`create_before_destroy` on `modules/certificates` keeps www, app and api serving through the swap.

Two Terraform facts that are outages if got wrong:

- **Branding must exist before the domain.** A `managed_login_version = 2` domain created without a
  branding record serves "Login pages unavailable" to every visitor. `depends_on` in
  `modules/auth/main.tf` is what orders them; it is not tidiness.
- **The AWS provider floor is `>= 6.12`.** `aws_cognito_managed_login_branding` exists in no 5.x
  release and in none before 6.12, which is what moved humbugg off the 5.x line.
  `refresh_token_rotation` was not the binding constraint — it has been available since 5.98.

## The option that was rejected

**Stay in-app** — keep the hand-written Amplify SRP screens. The case for it was real and is stronger
here than anywhere else in this repo: humbugg is a consumer product where sign-up *is* the funnel, the
hosted page cannot use `@ansavva/design-system`, it cannot be A/B tested, and it inserts a browser
hand-off in the middle of registration.

It lost on three counts. All six flows are hosted-page defaults, so the in-app versions are code
maintained for no differentiation. Password reset, forced password change and TOTP enrolment arrive
free and the in-app form could not do any of them. And rotation is unreachable without the code
flow — staying would have meant recording "no refresh-token rotation, permanently" as the price.

The funnel cost is real and unmitigated; it is the price paid, and Managed Login branding is where it
gets reduced later (`use_cognito_provided_values = true` today, Humbugg's palette when someone exports
a settings document for it).

## What a user notices

Everyone signed in at cut-over is signed out **once** — Amplify's tokens lived in AsyncStorage and
left with Amplify. No account is lost. At zero users, that cost was zero.

## Files

| Concern | Where |
|---|---|
| OAuth flow, token store, refresh, sign-out | `humbugg/app/src/auth/oauth.ts` |
| PKCE control test | `humbugg/app/src/auth/oauth.test.ts` |
| Session surface for the rest of the app | `humbugg/app/src/context/auth-context.tsx` |
| Sign-in launcher | `humbugg/app/src/screens/sign-in-launcher.tsx`, `src/app/(auth)/login.tsx` |
| Web callback route | `humbugg/app/src/app/auth/callback.tsx` |
| Consent capture | `humbugg/app/src/screens/dashboard.tsx` (`ProfileSetup`) |
| Client, branding, domain, alias records | `humbugg/infra/modules/auth/main.tf` |
| Registered redirects per environment | `humbugg/infra/envs/prod/main.tf`, `envs/dev/main.tf` |

The API was not touched. `Humbugg.Api/Program.cs` validates the **access** token and its `token_use`,
and the code flow issues exactly the same access token the SRP flow did.
