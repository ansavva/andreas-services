#!/usr/bin/env node
// Load a seed fixture (seeds/dev.json) into a dev stack, THROUGH THE LOCAL API.
//
// ## Why anything outside the app writes rows at all
//
// Humbugg's tipping points need several people. Free seats six participants,
// organizer included (PlanCatalog.EnsureParticipantCapacity), and the refusal a
// seventh gets — a 402 on POST /api/groups/{id}/join — is raised for a *different
// signed-in account* than the organizer. Free has no managed email invitations
// either (that is a Plus capability), so every joiner is a separate Cognito
// account, a separate profile, a separate join. Reaching the ceiling by hand is
// seven sign-ups in seven private windows, and every developer did it slightly
// differently or, more often, not at all. This loads the fixture once and the
// same way on every machine.
//
// ## Why a fixture file rather than flags
//
// Because the next thing to seed is a Plus exchange, and the one after that is
// whatever the test needs. A flag per field stops scaling at about six, and it
// puts the shape of the data in a shell script — where nobody reviews it and
// nothing validates it. `seeds/dev.json` is the answer to "what is on a
// developer's machine", in one place, in a diff.
//
// ## Why the rows go through the API and not DynamoDB
//
// The integration tier (Humbugg.Api.IntegrationTests) already mints JWTs and
// writes real rows, and it deletes them again — its users are subs that exist
// in no pool, so nobody can sign in as them afterwards. A seeder that wrote
// item shapes straight into the tables would be a third writer of those shapes
// and the one nobody re-reads when a field is added. So this signs in as each
// person over real SRP (the dev app client allows nothing weaker, the same
// posture as prod) and makes the requests the app makes: PUT /me, POST /groups,
// POST /groups/{id}/join, POST /groups/{id}/billing/plus/checkout. A malformed
// fixture fails with the API's own message, and a new required field breaks
// seeding loudly instead of writing rows the service has stopped agreeing with.
//
// It follows that the backend must be RUNNING (dev-up-backend.sh, which also
// starts the webhook consumer beside it) — for an exchange on Plus, Stripe
// delivers to this machine's public relay endpoint and that consumer applies
// it. The wrapper, scripts/dev-aws-seed.sh, checks the API and says so.
//
// ## Accounts are the wrapper's job
//
// A fixture person carries no password; the account must already exist. The
// wrapper creates every person before invoking this (one shared password from
// dev.env, never from a committed file), exactly the way dev-user.sh does for
// the single account — the two share ensure_pool_user in dev-aws-common.sh.
// This loader only signs in, and a sign-in that fails names the person and
// points back at the wrapper.
//
// ## Convergence
//
// Every load converges. A profile is PUT on every run (consent is captured
// once by the service and ignored after). An exchange is keyed on
// (organizer, name): a second run finds the one it made. A join by an existing
// member returns the group rather than failing, so nobody is added twice. A
// Plus exchange that already carries an entitlement is left alone. Rows that
// exist are LEFT ALONE even if the fixture has since changed — a seeded stack
// is somewhere people work — so a changed exchange is a new name.
//
// ## Plus, and why it is bought rather than granted
//
// The only writer of `plan = plus` is the Stripe webhook, and it should stay
// the only one. So this does what an organizer does: reserves the purchase
// (the backend creates a real test-mode Checkout Session), completes that very
// session with the Stripe CLI's fixture runner and `tok_visa` — the same
// private `payment_pages/{id}/confirm` call `stripe trigger` uses — and then
// polls the purchase status until the webhook has come back through this
// machine's relay. The CLI is pointed at the backend's own test key
// (STRIPE_API_KEY from dev.env, in the environment, never on argv) so it
// cannot confirm a session on some other account.
//
// ## Dev only
//
// The API base must be a loopback address. A loader whose target can be
// changed by one argument is a loader that eventually is; there is no prod
// mode and no flag that makes one.
//
// Usage (via the wrapper, normally):
//   node humbugg/scripts/dev-seed.mjs --fixture humbugg/seeds/dev.json [--check]
//
// Exit codes: 0 loaded (or, with --check, fully present); 1 not (yet) seeded;
// 2 refused — a guard or the fixture rejected the run and nothing was written.
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import pkg from 'amazon-cognito-identity-js';

const { CognitoUserPool, CognitoUser, AuthenticationDetails } = pkg;

const OK = 0;
const NOT_SEEDED = 1;
const REFUSED = 2;

// The consent version the app's signup checkbox records. The service captures
// it once per profile and ignores it after, so a stale value here re-seeds
// nothing wrong — but keep it the app's current one.
const CONSENT_VERSION = '2026-01';
// How long to wait for the webhook to come back through the relay after a
// confirmed Checkout. Stripe → gateway → queue → consumer → :5001 is usually
// under three seconds.
const WEBHOOK_WAIT_MS = 45_000;

class RefusedError extends Error {}
class NotSeeded extends Error {}

const ESC = String.fromCharCode(27);
const log = (message) => console.log(`${ESC}[1;34m[dev-seed]${ESC}[0m ${message}`);
const ok = (message) => console.log(`${ESC}[1;32m[ ok ]${ESC}[0m ${message}`);
const warn = (message) => console.error(`${ESC}[1;33m[warn]${ESC}[0m ${message}`);
const fail = (label, message) => console.error(`${ESC}[1;31m[${label}]${ESC}[0m ${message}`);

// ── dev.env ─────────────────────────────────────────────────────────────────────
// Same resolution as scripts/dev-aws-common.sh and app/e2e/support/dev-session.mjs.
const DEV_ENV_FILE =
  process.env.HUMBUGG_DEV_ENV_FILE ||
  path.join(
    process.env.XDG_CONFIG_HOME || path.join(homedir(), '.config'),
    'andreas-services',
    'humbugg',
    'dev.env',
  );

function parseEnvFile(file) {
  const values = {};
  for (const line of readFileSync(file, 'utf8').split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const separator = trimmed.indexOf('=');
    if (separator <= 0) continue;
    values[trimmed.slice(0, separator).trim()] = trimmed.slice(separator + 1).trim();
  }
  return values;
}

function devStack() {
  let env;
  try {
    env = parseEnvFile(DEV_ENV_FILE);
  } catch {
    throw new RefusedError(`${DEV_ENV_FILE} not found — run humbugg/scripts/dev-aws-setup.sh.`);
  }
  for (const key of ['COGNITO_USER_POOL_ID', 'COGNITO_CLIENT_ID', 'HUMBUGG_DEV_USER_PASSWORD']) {
    if (!env[key]) {
      throw new RefusedError(`${DEV_ENV_FILE} sets no ${key}. Run dev-aws-setup.sh, then dev-aws-seed.sh.`);
    }
  }
  const apiBase = (env.EXPO_PUBLIC_API_BASE_URL || 'http://127.0.0.1:5001/api').replace(/\/$/, '');
  const host = new URL(apiBase).hostname;
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(host)) {
    throw new RefusedError(
      `Refusing: API base ${apiBase} is not a loopback address. This loader seeds a local dev stack only.`,
    );
  }
  return {
    apiBase,
    userPoolId: env.COGNITO_USER_POOL_ID,
    clientId: env.COGNITO_CLIENT_ID,
    password: env.HUMBUGG_DEV_USER_PASSWORD,
    stripeSecretKey: env.HUMBUGG_STRIPE_SECRET_KEY || '',
    stripeMode: env.HUMBUGG_STRIPE_MODE || 'disabled',
    plusPriceCents: Number(env.HUMBUGG_PLUS_PRICE_CENTS || 1200),
  };
}

// ── The fixture ─────────────────────────────────────────────────────────────────
function loadFixture(file) {
  let raw;
  try {
    raw = JSON.parse(readFileSync(file, 'utf8'));
  } catch (error) {
    throw new RefusedError(`Cannot read fixture ${file}: ${error.message}`);
  }
  const people = raw.people ?? [];
  const exchanges = raw.exchanges ?? [];
  if (people.length === 0) throw new RefusedError('Fixture names no people.');
  const byHandle = new Map();
  for (const person of people) {
    for (const key of ['handle', 'email', 'displayName']) {
      if (!person[key]) throw new RefusedError(`A person is missing "${key}".`);
    }
    if (!person.email.endsWith('.test')) {
      throw new RefusedError(
        `Refusing: "${person.email}" is not a .test address. Only RFC 2606 reserved addresses belong in a fixture.`,
      );
    }
    if (byHandle.has(person.handle)) throw new RefusedError(`Duplicate handle "${person.handle}".`);
    byHandle.set(person.handle, person);
  }
  const seen = new Set();
  for (const exchange of exchanges) {
    for (const key of ['handle', 'name', 'organizer', 'plan']) {
      if (!exchange[key]) throw new RefusedError(`Exchange "${exchange.handle ?? '?'}" is missing "${key}".`);
    }
    if (!['free', 'plus'].includes(exchange.plan)) {
      throw new RefusedError(`Exchange "${exchange.handle}": plan must be "free" or "plus".`);
    }
    const key = `${exchange.organizer} ${exchange.name}`;
    if (seen.has(key)) {
      throw new RefusedError(
        `Two exchanges by "${exchange.organizer}" are both named "${exchange.name}"; the name is the key.`,
      );
    }
    seen.add(key);
    for (const handle of [exchange.organizer, ...(exchange.participants ?? [])]) {
      if (!byHandle.has(handle)) {
        throw new RefusedError(`Exchange "${exchange.handle}" refers to unknown handle "${handle}".`);
      }
    }
    if ((exchange.participants ?? []).includes(exchange.organizer)) {
      throw new RefusedError(`Exchange "${exchange.handle}": the organizer participates already; do not list them.`);
    }
  }
  return { people, exchanges, byHandle };
}

// ── Sessions ────────────────────────────────────────────────────────────────────
// Real SRP, the same as app/e2e/support/dev-session.mjs and smoke-session.mjs,
// for the same reason: the dev client allows nothing weaker.
function signIn({ userPoolId, clientId }, email, password) {
  const user = new CognitoUser({
    Username: email,
    Pool: new CognitoUserPool({ UserPoolId: userPoolId, ClientId: clientId }),
  });
  return new Promise((resolve, reject) => {
    user.authenticateUser(new AuthenticationDetails({ Username: email, Password: password }), {
      onSuccess: (session) => resolve(session.getAccessToken().getJwtToken()),
      onFailure: (error) =>
        reject(
          new RefusedError(
            `Cannot sign in as ${email}: ${error.message}. Run humbugg/scripts/dev-aws-seed.sh (not this loader directly) so the account exists with the dev.env password.`,
          ),
        ),
      newPasswordRequired: () =>
        reject(new RefusedError(`${email} demands a new password — re-run humbugg/scripts/dev-aws-seed.sh.`)),
    });
  });
}

class ApiError extends Error {
  constructor(status, body) {
    super(body);
    this.status = status;
  }
}

function client(apiBase, token) {
  return async (method, apiPath, body) => {
    const response = await fetch(`${apiBase}${apiPath}`, {
      method,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
      throw new ApiError(response.status, `${method} ${apiPath} -> ${response.status}: ${await response.text()}`);
    }
    return response.status === 204 ? undefined : response.json();
  };
}

// ── People ──────────────────────────────────────────────────────────────────────
async function seedPeople(stack, people, check) {
  const sessions = new Map();
  for (const person of people) {
    // --check signs in too: the loader has no other way to see a profile or a
    // group, and a correct SRP sign-in trips no lockout. It is still a sign-in,
    // which is why dev-user.sh --check stops short of one.
    const api = client(stack.apiBase, await signIn(stack, person.email, stack.password));
    sessions.set(person.handle, api);
    if (check) {
      try {
        await api('GET', '/me');
        ok(`profile present: ${person.handle} (${person.email})`);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) throw new NotSeeded(`no profile for ${person.handle}`);
        throw error;
      }
      continue;
    }
    await api('PUT', '/me', {
      display_name: person.displayName,
      consent: { version: CONSENT_VERSION, accepted_at: new Date().toISOString() },
    });
    ok(`profile: ${person.handle} (${person.email})`);
  }
  return sessions;
}

// ── Exchanges ───────────────────────────────────────────────────────────────────
// The invite secret is shown ONCE, on creation, and thereafter only by rotating it
// (POST /groups/{id}/invite) — the service stores a hash, and GET /groups/{id}
// carries no link. So a fresh exchange joins everyone with the link it was born
// with, and a re-run rotates only when somebody in the fixture is still missing:
// a rotation invalidates whatever link a human copied out of the app.
function inviteToken(inviteUrl) {
  const marker = '#invite=';
  const at = (inviteUrl ?? '').indexOf(marker);
  if (at < 0) throw new Error(`No invite secret in "${inviteUrl}".`);
  return inviteUrl.slice(at + marker.length);
}

async function findExchange(api, exchange) {
  const groups = await api('GET', '/groups');
  return groups.find((group) => group.name === exchange.name && group.is_owner);
}

async function seedExchange(stack, sessions, byHandle, exchange, check, links) {
  const asOrganizer = sessions.get(exchange.organizer);
  let groupId = (await findExchange(asOrganizer, exchange))?.group_id;
  let inviteUrl = null;
  if (!groupId) {
    if (check) throw new NotSeeded(`exchange "${exchange.name}" does not exist`);
    const created = await asOrganizer('POST', '/groups', {
      name: exchange.name,
      description: exchange.description ?? null,
      event_date: exchange.eventDate ?? null,
      spending_limit: exchange.spendingLimit ?? null,
    });
    groupId = created.group_id;
    inviteUrl = created.invite_url;
    ok(`exchange created: ${exchange.handle} ("${exchange.name}")`);
  } else {
    log(`exchange exists: ${exchange.handle} ("${exchange.name}")`);
  }
  const detail = await asOrganizer('GET', `/groups/${groupId}`);
  const memberNames = new Set((detail.members ?? []).map((member) => member.display_name));
  const missing = (exchange.participants ?? []).filter((handle) => !memberNames.has(byHandle.get(handle).displayName));

  if (check) {
    if (missing.length > 0) throw new NotSeeded(`${missing.join(', ')} not in "${exchange.name}"`);
  } else if (missing.length > 0) {
    if (!inviteUrl) {
      inviteUrl = (await asOrganizer('POST', `/groups/${groupId}/invite`)).invite_url;
      log('  rotated the invite link (the old one is void)');
    }
    const token = inviteToken(inviteUrl);
    for (const handle of missing) {
      try {
        await sessions.get(handle)('POST', `/groups/${groupId}/join`, { invite_token: token });
        ok(`  joined: ${handle}`);
      } catch (error) {
        if (error instanceof ApiError && error.status === 402) {
          throw new RefusedError(
            `Refusing: "${exchange.name}" cannot seat ${handle} — the API answered 402 (${error.message}). ` +
              `The fixture asks for more participants than the plan allows; raise HUMBUGG_FREE_PARTICIPANT_LIMIT in ${DEV_ENV_FILE} or shorten the list.`,
          );
        }
        throw error;
      }
    }
  }
  if (inviteUrl) links.push({ exchange, inviteUrl });

  if (exchange.plan === 'plus') {
    await ensurePlus(stack, asOrganizer, groupId, exchange, byHandle.get(exchange.organizer), check);
  }
}

// ── Plus ────────────────────────────────────────────────────────────────────────
async function ensurePlus(stack, asOrganizer, groupId, exchange, organizer, check) {
  const status = await asOrganizer('GET', `/groups/${groupId}/billing/plus`);
  if (status.entitlement_id) {
    (check ? ok : log)(`  Plus already on: ${exchange.handle}`);
    return;
  }
  if (check) throw new NotSeeded(`"${exchange.name}" is not on Plus`);
  if (stack.stripeMode !== 'test' || !stack.stripeSecretKey.startsWith('sk_test_')) {
    throw new RefusedError(
      `Refusing: "${exchange.name}" wants Plus, but ${DEV_ENV_FILE} has no test-mode Stripe key (HUMBUGG_STRIPE_MODE=test, HUMBUGG_STRIPE_SECRET_KEY=sk_test_…). See docs/stripe-setup.md.`,
    );
  }
  if (spawnSync('stripe', ['--version'], { stdio: 'ignore' }).status !== 0) {
    throw new RefusedError(
      'Refusing: the `stripe` CLI is not installed; it is what completes the test Checkout. humbugg/scripts/dev-setup.sh installs it.',
    );
  }

  const checkout = await asOrganizer('POST', `/groups/${groupId}/billing/plus/checkout`);
  log(`  reserved Plus purchase, Checkout Session ${checkout.session_id}`);

  // The CLI's fixture runner against the SESSION THE BACKEND MADE: a payment
  // method from tok_visa, then the same payment_pages confirm that `stripe
  // trigger checkout.session.completed` performs on its own throwaway session.
  // expected_amount is the plan's price, so a price change in dev.env that the
  // running backend has not picked up fails here, not as a mismatch the webhook
  // rejects later.
  const dir = mkdtempSync(path.join(tmpdir(), 'humbugg-dev-seed-'));
  const fixtureFile = path.join(dir, 'confirm-checkout.json');
  writeFileSync(
    fixtureFile,
    JSON.stringify({
      _meta: { template_version: 0 },
      fixtures: [
        {
          name: 'payment_method',
          path: '/v1/payment_methods',
          method: 'post',
          params: {
            type: 'card',
            card: { token: 'tok_visa' },
            billing_details: { email: organizer.email, name: organizer.displayName },
          },
        },
        {
          name: 'confirm',
          path: `/v1/payment_pages/${checkout.session_id}/confirm`,
          method: 'post',
          params: { payment_method: '${payment_method:id}', expected_amount: stack.plusPriceCents },
        },
      ],
    }),
  );
  try {
    const result = spawnSync('stripe', ['fixtures', fixtureFile], {
      env: { ...process.env, STRIPE_API_KEY: stack.stripeSecretKey },
      encoding: 'utf8',
    });
    if (result.status !== 0) {
      throw new Error(
        `stripe fixtures failed (exit ${result.status}):\n${result.stderr || result.stdout}\n` +
          `The purchase is still pending; complete it by hand at ${checkout.checkout_url} with card 4242 4242 4242 4242.`,
      );
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
  log('  Checkout confirmed with tok_visa; waiting for the webhook through the relay…');

  const deadline = Date.now() + WEBHOOK_WAIT_MS;
  while (Date.now() < deadline) {
    const current = await asOrganizer('GET', `/groups/${groupId}/billing/plus`);
    if (current.entitlement_id) {
      ok(`  Plus on: ${exchange.handle} (${current.entitlement_id})`);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  throw new NotSeeded(
    `Stripe took the payment for "${exchange.name}" but no webhook reached the backend in ${WEBHOOK_WAIT_MS / 1000}s. ` +
      'Is the webhook-consumer container running (humbugg/scripts/dev-up-backend.sh starts it with the API)? The event ' +
      'is waiting in this machine\'s queue; start it and the exchange flips to Plus on its own — then re-run to confirm.',
  );
}

// ── main ────────────────────────────────────────────────────────────────────────
function parseArgs(argv) {
  const args = { fixture: null, check: false };
  for (let i = 0; i < argv.length; i++) {
    switch (argv[i]) {
      case '--fixture':
        args.fixture = argv[++i];
        break;
      case '--check':
        args.check = true;
        break;
      case '-h':
      case '--help':
        console.log('Usage: node dev-seed.mjs --fixture <seeds/dev.json> [--check]');
        process.exit(OK);
        break;
      default:
        throw new RefusedError(`Unknown argument: ${argv[i]}`);
    }
  }
  if (!args.fixture) throw new RefusedError('--fixture is required.');
  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const fixture = loadFixture(args.fixture);
  const stack = devStack();

  try {
    const health = await fetch(`${stack.apiBase.replace(/\/api$/, '')}/health`);
    if (!health.ok) throw new Error(`status ${health.status}`);
  } catch (error) {
    throw new RefusedError(`No API at ${stack.apiBase} (${error.message}). Start it: humbugg/scripts/dev-up.sh`);
  }

  log(`${args.check ? 'Checking' : 'Loading'} ${path.basename(args.fixture)} against ${stack.apiBase}`);
  const sessions = await seedPeople(stack, fixture.people, args.check);
  const links = [];
  for (const exchange of fixture.exchanges) {
    await seedExchange(stack, sessions, fixture.byHandle, exchange, args.check, links);
  }
  ok(args.check ? 'This machine matches the fixture.' : 'Loaded.');
  // The link is the one thing a human cannot read back: print it while we have
  // it. Local only, and the secret is void the moment anyone taps Invite.
  for (const { exchange, inviteUrl } of links) log(`invite link for ${exchange.handle}: ${inviteUrl}`);
  if (!args.check && links.length === 0 && fixture.exchanges.length > 0) {
    log('Nothing joined, so no invite link was minted. As the organizer, tap Invite in the app to get one.');
  }
  return OK;
}

main().then(
  (code) => process.exit(code),
  (error) => {
    if (error instanceof RefusedError) {
      fail('refused', error.message);
      process.exit(REFUSED);
    }
    if (error instanceof NotSeeded) {
      warn(error.message);
      process.exit(NOT_SEEDED);
    }
    fail('error', error.stack ?? error.message);
    process.exit(NOT_SEEDED);
  },
);
