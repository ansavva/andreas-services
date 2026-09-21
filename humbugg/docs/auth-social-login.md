# Social sign-in: Google, Apple, Facebook, LinkedIn

Decision record and operator runbook. Decided and built September 2026, on top of
[`auth-managed-login.md`](auth-managed-login.md), which it does not replace.

## The decision

**Four providers, as Cognito identity providers on the existing pool, rendered as buttons on the
existing Managed Login page.** The app changed by zero lines: the hosted page grows buttons above the
password form, the callback and the token exchange are what they were.

| Provider | Verdict | Why |
|---|---|---|
| **Google** | in | Native Cognito type. Largest coverage. Says `email_verified`. |
| **Apple** | in — **required** | App Store Review Guideline 4.8: an iOS app offering any third-party sign-in must offer Sign in with Apple. `humbugg/app` exists to ship to the stores. |
| **Facebook** | in | Native Cognito type. Meta's consumer identity. |
| **LinkedIn** | in, marginal | Generic OIDC ("Sign In with LinkedIn using OpenID Connect"). Fits the office-Secret-Santa segment the marketing targets. The one provider Cognito has no native type for. |
| **Instagram** | **out — not possible** | Instagram offers no consumer sign-in. The Basic Display API was retired in December 2024; "Instagram API with Instagram Login" is a content-management API for business and creator accounts, is not OIDC and returns no email. Facebook Login *is* Meta's identity product. |
| Microsoft, X, others | out | No audience fit. |

## The one design problem: account linking

Every humbugg row keys on the Cognito `sub`. Cognito's default for a federated sign-in is a **new
user** — `google_<id>`, its own sub — even when a password account with the same email exists. Alice
clicks "Continue with Google" and finds an empty Humbugg. The reverse also breaks: a Google-first
Alice can never sign up with a password, because the email is taken by a user she cannot reset.

**Fix: a pre-sign-up trigger, `scripts/auth-trigger/pre-sign-up.mjs`, packaged by
`infra/modules/auth/pre_sign_up.tf`.** On `PreSignUp_ExternalProvider` it links the federated
identity onto a **native** user — the one already there, or one it creates on the spot with a random
*permanent* password and `email_verified=true`. The native user is always the canonical sub; the
social identity is an alias of it. Password recovery therefore works for everyone, which is why the
password is permanent: `AdminCreateUser` alone leaves `FORCE_CHANGE_PASSWORD`, a state
forgot-password refuses to act on. Native sign-ups pass through untouched.

Linking by email is a trust decision. Whoever a provider says owns `alice@example.com` gets Alice's
Humbugg. That is the trust every email-based password reset already extends; every provider wired in
verifies an address before returning it, and an explicit `email_verified=false` from one that says so
refuses the link.

**Cognito gives a trigger 5 seconds, whatever the Lambda's timeout, and a late reply is a failed
sign-in.** Measured on a dev stack: the cold create path timed out at 256 MB and took 2.3 s at
1024 MB. The memory is CPU; it is not oversized.

**The "first link fails once" quirk did not occur.** Cognito historically failed the first
federated sign-in that performed a link with "Already found an entry for username google_…" and
succeeded on the second click. Measured 2026-09-21 on the shared dev pool with a real Google client:
password-first → Google linked onto the existing sub and landed in the app on the first click. If it
ever reappears, the mitigation is a one-shot retry in `app/src/auth/oauth.ts`'s callback handling,
not anything in the trigger.

**Three things the first live sign-ins did find, all fixed the same day:**

- **LinkedIn linked under an id LinkedIn never issued.** The pool is case-insensitive, so Cognito
  hands the trigger a LOWERCASED federated username — `linkedin_mdrhj2asx8` for a real `sub` of
  `MDRHj2Asx8` — and a link made from it fails every later sign-in with "Invalid ProviderName/Username
  combination". Google's subs are digits, which is why Google never showed it. Every provider now
  maps its `sub` into `custom:idp_sub` verbatim (an in-place pool change, measured), and the trigger
  links with that; the username is only a fallback. LinkedIn-first then landed first click.

- The trigger refused Google with "That provider has not verified your email address." Cognito
  hands every federated user `email_verified=false` as a placeholder when the claim is not mapped —
  indistinguishable from a provider saying so. Google, Apple and LinkedIn now map their real claim
  and the trigger checks it only for them (`HUMBUGG_EMAIL_VERIFIED_PROVIDERS`); Facebook has no
  claim and is never checked.
- Sign-out signed you straight back in. `logout()` adopted "signed out" before `signOut()` reached
  `/logout`; the protected layout mounted `SignInRedirect`, its authorize won the race, and
  Cognito's still-live session cookie answered it silently. Pre-existing; a password retype had
  masked it. `signOut` now navigates first and web never adopts.

## What each provider needs from you

Everything below is console work outside this repo. Each provider is **independent and optional** —
an empty id leaves that provider off the page — so they can land one at a time. The value every
console asks for is this stack's redirect URI:

| Stack | Redirect URI to register |
|---|---|
| prod | `https://auth.humbugg.com/oauth2/idpresponse` |
| dev — every machine | `https://humbugg-dev.auth.us-east-1.amazoncognito.com/oauth2/idpresponse` |

Cognito matches it exactly. Two URIs, registered once, and that is the whole reason the dev pool is
shared (`infra/envs/dev-shared`): it was per machine until September 2026, and a per-machine Managed
Login domain meant a new machine was a console edit at all four providers before its developer could
sign in with any of them.

**Two credentials per provider, one project/app.** Where the console allows several clients under
one app — Google does — make a `Humbugg prod` and a `Humbugg dev` client, each with only its own
redirect URI, so the dev secret every developer's `dev.env` holds can never be prod's. Facebook,
LinkedIn and Apple take one list of URIs per app; put both on it.

### Google

1. [console.cloud.google.com](https://console.cloud.google.com) → a project (any; `humbugg`).
2. **APIs & Services → OAuth consent screen.** User type *External*. App name `Humbugg`, support
   email, **authorized domain `humbugg.com`**, privacy policy `https://www.humbugg.com/privacy`, terms
   `https://www.humbugg.com/terms`. Scopes: `openid`, `email`, `profile` only — all non-sensitive, so
   **no verification review is needed**. Then *Publish app* (leave Testing and only listed test users
   can sign in).
3. **Credentials → Create credentials → OAuth client ID.** Type **Web application** — Cognito is
   the OAuth client, exchanging the code server-side with a secret; the iOS/Android types have no
   secret and no redirect. Name `Humbugg prod`, one authorized redirect URI: prod's. No JavaScript
   origins.
4. A second Web client, `Humbugg dev`, with the dev URI.
5. Copy each **Client ID** and **Client secret**.

### Apple

1. [developer.apple.com](https://developer.apple.com) — Apple Developer Program membership
   ($99/year) on the account that will publish the app.
2. **Certificates, Identifiers & Profiles → Identifiers → App IDs**: the app's bundle id
   (`com.humbugg.app`, matching `app/app.json`), capability *Sign in with Apple* ticked.
3. **Identifiers → Services IDs → +**: identifier `com.humbugg.auth` (this is the "client id"),
   *Sign in with Apple* → Configure: primary App ID from step 2, **domains `auth.humbugg.com` and
   `humbugg-dev.auth.us-east-1.amazoncognito.com`**, return URLs both redirect URIs above.
4. **Keys → +**: name `Humbugg Sign in with Apple`, tick *Sign in with Apple*, configure to the App
   ID. Download the `.p8` **once** — Apple never shows it again. Note the **Key ID**.
5. Your **Team ID** is top-right of the membership page.
6. **Private Email Relay — do this or mail to Apple users bounces.** Some users hide their address;
   Apple hands us `xxxx@privaterelay.appleid.com` and only forwards mail from registered senders.
   *Services → Sign in with Apple for Email Communication*: register the domain `humbugg.com` and
   the sender `no-reply@humbugg.com` (SES's From address). SPF and DKIM are already in place for
   the domain, which Apple requires.

Values: `apple_services_id` = `com.humbugg.auth`, `apple_team_id`, `apple_key_id`,
`apple_private_key` = the `.p8` file's contents.

### Facebook (Meta)

1. [developers.facebook.com](https://developers.facebook.com) → **Create App** → use case
   *Authenticate and request data from users with Facebook Login* (a "Consumer" app).
2. **Facebook Login → Settings**: *Client OAuth login* and *Web OAuth login* on, **Valid OAuth
   Redirect URIs** = the redirect URI(s) above.
3. **App settings → Basic**: privacy policy URL `https://www.humbugg.com/privacy`, terms
   `https://www.humbugg.com/terms`, **User data deletion** — pick *Data deletion instructions URL*
   and give `https://www.humbugg.com/privacy` (the policy's deletion section satisfies it; Meta
   accepts instructions, not only a callback). App icon 1024×1024, category *Utility & productivity*.
   Save; note the **App ID** and **App Secret** (Show).
4. **Switch the app to Live** (toggle at the top). Until it is Live only app admins and testers can
   sign in. `public_profile` and `email` are default permissions and need **no App Review**.
   **Business verification IS required** — this doc first said it was not, and the Live toggle
   refused on 2026-09-21 until the *Andreas Services* business portfolio is verified. That is
   Meta's document flow (business registration or similar, plus a phone/domain check), reviewed in
   days rather than minutes, run from business.facebook.com → Security Centre → *Start
   verification*. The dev test can proceed in Development mode meanwhile — an app admin can sign in
   to a Development-mode app — so the credentials are still worth putting in `dev.env` now.

**State on 2026-09-21:** a Humbugg app (`363719051061656`, Consumer type, Facebook Login product
already added) existed on the developer account and is linked to the *Andreas Services* portfolio.
Redirect URIs, app domain, terms, deletion URL, contact and category are set; the app icon is not.
Dev sign-in verified in Development mode. Live waits on business verification.

### LinkedIn

1. [linkedin.com/developers](https://www.linkedin.com/developers) → **Create app**. It must be
   associated with a **LinkedIn Company Page** — create a Humbugg page first if none exists; the
   page admin must verify the app from the page.
2. **Products** tab → request **Sign In with LinkedIn using OpenID Connect**. Self-serve, granted
   immediately.
3. **Auth** tab: **Authorized redirect URLs for your app** = the redirect URI(s) above. Copy the
   **Client ID** and **Primary Client Secret**.

## Where the values go

### Production — GitHub, environment `humbugg-production`

Repository → Settings → Environments → `humbugg-production`. Ids are **variables**, secrets are
**secrets**; the deploy reads both as `TF_VAR_*` (`.github/workflows/humbugg-prod.yaml`).

| Kind | Name | Value |
|---|---|---|
| variable | `HUMBUGG_GOOGLE_CLIENT_ID` | Google client id |
| secret | `HUMBUGG_GOOGLE_CLIENT_SECRET` | Google client secret |
| variable | `HUMBUGG_APPLE_SERVICES_ID` | `com.humbugg.auth` |
| variable | `HUMBUGG_APPLE_TEAM_ID` | Team ID |
| variable | `HUMBUGG_APPLE_KEY_ID` | Key ID |
| secret | `HUMBUGG_APPLE_PRIVATE_KEY` | the `.p8` contents, pasted as-is with its line breaks |
| variable | `HUMBUGG_FACEBOOK_APP_ID` | Meta app id |
| secret | `HUMBUGG_FACEBOOK_APP_SECRET` | Meta app secret |
| variable | `HUMBUGG_LINKEDIN_CLIENT_ID` | LinkedIn client id |
| secret | `HUMBUGG_LINKEDIN_CLIENT_SECRET` | LinkedIn primary client secret |

Then run the prod workflow with `run_infra=true` (or merge anything under `humbugg/infra/**`). The
apply creates each provider whose id is set and lists it on the client; the button appears on
`auth.humbugg.com` on the next page load. Unset ones are simply absent.

`gh` from a local machine can set them without the browser:

```bash
gh variable set HUMBUGG_GOOGLE_CLIENT_ID --env humbugg-production --body '…'
```

```bash
gh secret set HUMBUGG_GOOGLE_CLIENT_SECRET --env humbugg-production
```

```bash
gh secret set HUMBUGG_APPLE_PRIVATE_KEY --env humbugg-production < AuthKey_XXXXXXXXXX.p8
```

### Dev — `~/.config/andreas-services/humbugg/dev.env`

Uncomment and fill the keys in the *Social sign-in* block (`dev.env.sample` shows them; the Apple
key travels base64 on one line because an env file cannot hold a PEM), then re-run
`./humbugg/scripts/dev-aws-setup.sh`. The values come from the team password manager. The pool is
shared, so the run applies them for every machine at once, and the button is on the dev Managed
Login page for all of them.

**The guard.** Every machine applies the shared stack on every run, from its own `dev.env`, and
Terraform cannot tell "this machine has no Google keys" from "remove Google". So the script refuses
to apply the shared stack while the pool holds a provider the machine has no id for, naming the key.
Three ways on: put the keys in (the normal one); `--skip-shared` to use the pool exactly as it is;
`--allow-provider-removal` to apply with only the providers this machine names — the one way to take
a provider off the pool. All three were exercised against the live pool when this landed.

Not SSM and not GitHub, deliberately: GitHub secrets are readable only inside an Actions run, and the
shared stack is applied from laptops; SSM would be a third place to hand-manage the same secret.
`dev.env` is the one file a machine already has, and the password manager is where it comes from.

## Verifying

On the shared dev pool with Google set:

1. `./humbugg/scripts/dev-up.sh`, open `http://localhost:8081`, reach the hosted page: a
   *Continue with Google* button sits above the form.
2. **Password-first, then Google.** Sign up with a password using a Google-owned address, confirm,
   create an exchange. Sign out. *Continue with Google* with the same address → the same exchange is
   there. `aws cognito-idp admin-get-user --username <email>` shows one user with
   `identities` naming Google. **Passed 2026-09-21, first click.**
3. **Google-first, then password.** A fresh Google address → lands in the app, profile setup as
   usual. Sign out. *Forgot password* with that address → a code arrives, a password is set, password
   sign-in reaches the same account. **Passed 2026-09-21** — one sub through sign-out, a second
   Google sign-in (no trigger call: already linked), the reset and the password sign-in.
4. **LinkedIn-first.** The generic-OIDC path. **Passed 2026-09-21** after the `custom:idp_sub` fix
   above; the log line carries `usernameSubjectDiffers: true`, the finding kept visible.
5. **Facebook onto an existing account.** **Passed 2026-09-21** in Development mode (admin only)
   — third identity on the same sub. Two findings on the way: a stale grant from an earlier
   attempt returned no email until the app was removed from the account's *Apps and websites*;
   and with `custom:idp_sub → id` mapped, Cognito's attribute fetch returned only the username
   ("attributes required: [email]") while the identical Graph call from the API Explorer returned
   the email. Facebook maps the four plain fields only; its ids are digits, so the username
   fallback is exact.
4. `aws logs tail /aws/lambda/humbugg-dev-auth-pre-sign-up` shows one `linked federated identity`
   line per first sign-in, naming the sub and never the email.

Production is verified the same way in a browser, by a person, after the apply.

## What a user notices

Nothing changes for anyone signed in. Existing password accounts keep working and gain the buttons.
Someone who signs in with a provider whose email matches their existing account is in their existing
account. Someone whose provider gives a *different* address than they registered with gets a second,
empty account — as they would anywhere; the fix is to sign in the old way.

## Files

| Concern | Where |
|---|---|
| Providers, the client's list, the trigger, its grant | `infra/modules/auth/identity_providers.tf`, `pre_sign_up.tf` |
| The trigger and its tests | `scripts/auth-trigger/pre-sign-up.mjs`, `pre-sign-up.test.mjs` |
| Prod values | `.github/workflows/humbugg-prod.yaml` (`TF_VAR_*`), `infra/envs/prod/variables.tf` |
| Dev values | `dev.env` → `scripts/dev-aws-common.sh` `add_social_login_vars` → `infra/envs/dev-shared` |
| Disclosure | `marketing/src/pages/PrivacyPage.tsx` §2; `docs/gdpr-compliance.md` §7 says why the providers are controllers, not sub-processors |
