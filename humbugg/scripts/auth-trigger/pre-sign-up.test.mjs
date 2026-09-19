// `node --test humbugg/scripts/auth-trigger/pre-sign-up.test.mjs` — no install,
// no AWS. The handler takes its Cognito calls as one object, and this hands it
// a recorder.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createHandler, parseFederatedUsername } from './pre-sign-up.mjs';

const PROVIDERS = ['Google', 'Facebook', 'SignInWithApple', 'LinkedIn'];
const POOL = 'us-east-1_test';

function fakeCognito({ users = [] } = {}) {
  const calls = [];
  const record = (name) => async (input) => {
    calls.push({ name, input });
    if (name === 'listUsers') return { Users: users };
    if (name === 'adminCreateUser') {
      return { User: { Username: 'new-native-uuid', UserStatus: 'FORCE_CHANGE_PASSWORD' } };
    }
    return {};
  };
  return {
    calls,
    listUsers: record('listUsers'),
    adminConfirmSignUp: record('adminConfirmSignUp'),
    adminUpdateUserAttributes: record('adminUpdateUserAttributes'),
    adminCreateUser: record('adminCreateUser'),
    adminSetUserPassword: record('adminSetUserPassword'),
    adminLinkProviderForUser: record('adminLinkProviderForUser'),
  };
}

function externalEvent(userName, userAttributes) {
  return {
    triggerSource: 'PreSignUp_ExternalProvider',
    userPoolId: POOL,
    userName,
    request: { userAttributes },
    response: { autoConfirmUser: false, autoVerifyEmail: false, autoVerifyPhone: false },
  };
}

const names = (calls) => calls.map((c) => c.name);

test.beforeEach(() => {
  process.env.HUMBUGG_IDENTITY_PROVIDERS = PROVIDERS.join(',');
});

test('parses a federated username back to the declared provider name', () => {
  assert.deepEqual(parseFederatedUsername('google_1234', PROVIDERS), {
    providerName: 'Google',
    providerUserId: '1234',
  });
  assert.deepEqual(parseFederatedUsername('signinwithapple_001234.abcd_ef', PROVIDERS), {
    providerName: 'SignInWithApple',
    providerUserId: '001234.abcd_ef',
  });
  assert.equal(parseFederatedUsername('twitter_1', PROVIDERS), null);
  assert.equal(parseFederatedUsername('nounderscore', PROVIDERS), null);
});

test('native sign-ups pass through untouched', async () => {
  const cognito = fakeCognito();
  const event = { triggerSource: 'PreSignUp_SignUp', userPoolId: POOL, userName: 'uuid', request: {}, response: {} };
  assert.equal(await createHandler(cognito)(event), event);
  assert.deepEqual(cognito.calls, []);
});

test('first social sign-in creates a confirmed native user and links onto it', async () => {
  const cognito = fakeCognito();
  const event = externalEvent('google_42', {
    email: 'Alice@Example.com',
    email_verified: 'true',
    given_name: 'Alice',
    family_name: 'Example',
  });

  assert.equal(await createHandler(cognito)(event), event);
  assert.deepEqual(names(cognito.calls), ['listUsers', 'adminCreateUser', 'adminSetUserPassword', 'adminLinkProviderForUser']);

  const [list, create, password, link] = cognito.calls.map((c) => c.input);
  assert.equal(list.Filter, 'email = "alice@example.com"');
  assert.equal(create.Username, 'alice@example.com');
  assert.equal(create.MessageAction, 'SUPPRESS');
  assert.deepEqual(create.UserAttributes, [
    { Name: 'email', Value: 'alice@example.com' },
    { Name: 'email_verified', Value: 'true' },
    { Name: 'given_name', Value: 'Alice' },
    { Name: 'family_name', Value: 'Example' },
  ]);
  assert.equal(password.Username, 'new-native-uuid');
  assert.equal(password.Permanent, true);
  assert.ok(password.Password.length >= 12);
  assert.match(password.Password, /[A-Z]/);
  assert.match(password.Password, /[a-z]/);
  assert.match(password.Password, /[0-9]/);
  assert.deepEqual(link, {
    UserPoolId: POOL,
    DestinationUser: { ProviderName: 'Cognito', ProviderAttributeValue: 'new-native-uuid' },
    SourceUser: { ProviderName: 'Google', ProviderAttributeName: 'Cognito_Subject', ProviderAttributeValue: '42' },
  });
});

test('an existing confirmed password account is linked, not recreated', async () => {
  const cognito = fakeCognito({
    users: [
      { Username: 'existing-uuid', UserStatus: 'CONFIRMED', Attributes: [{ Name: 'email_verified', Value: 'true' }] },
    ],
  });
  await createHandler(cognito)(externalEvent('facebook_7', { email: 'alice@example.com' }));
  assert.deepEqual(names(cognito.calls), ['listUsers', 'adminLinkProviderForUser']);
  assert.equal(cognito.calls[1].input.DestinationUser.ProviderAttributeValue, 'existing-uuid');
  assert.equal(cognito.calls[1].input.SourceUser.ProviderName, 'Facebook');
});

test('an unconfirmed, unverified password account is confirmed and verified before linking', async () => {
  const cognito = fakeCognito({
    users: [{ Username: 'pending-uuid', UserStatus: 'UNCONFIRMED', Attributes: [{ Name: 'email_verified', Value: 'false' }] }],
  });
  await createHandler(cognito)(externalEvent('linkedin_abc', { email: 'alice@example.com', email_verified: 'true' }));
  assert.deepEqual(names(cognito.calls), ['listUsers', 'adminConfirmSignUp', 'adminUpdateUserAttributes', 'adminLinkProviderForUser']);
  assert.deepEqual(cognito.calls[2].input.UserAttributes, [{ Name: 'email_verified', Value: 'true' }]);
});

test('a federated-only record with the same email is never the link target', async () => {
  const cognito = fakeCognito({ users: [{ Username: 'google_1', UserStatus: 'EXTERNAL_PROVIDER' }] });
  await createHandler(cognito)(externalEvent('facebook_7', { email: 'alice@example.com' }));
  assert.deepEqual(names(cognito.calls), ['listUsers', 'adminCreateUser', 'adminSetUserPassword', 'adminLinkProviderForUser']);
});

test('refuses an identity without an email, or with one the provider says is unverified', async () => {
  const cognito = fakeCognito();
  const handler = createHandler(cognito);
  await assert.rejects(handler(externalEvent('google_1', {})), /no email address/);
  await assert.rejects(handler(externalEvent('google_1', { email: 'a@b.c', email_verified: 'false' })), /not verified/);
  assert.deepEqual(cognito.calls, []);
});

test('refuses a username from a provider the pool does not declare', async () => {
  const cognito = fakeCognito();
  await assert.rejects(createHandler(cognito)(externalEvent('twitter_1', { email: 'a@b.c' })), /Unrecognised/);
  assert.deepEqual(cognito.calls, []);
});
