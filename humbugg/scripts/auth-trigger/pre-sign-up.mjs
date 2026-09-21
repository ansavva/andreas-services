// Cognito's pre-sign-up trigger, and it does one thing: make a social sign-in
// land on the SAME account as the email/password one.
//
// Every humbugg row keys on the Cognito `sub` — profiles, groups, members,
// draws, billing. Left alone, Cognito gives a Google sign-in its own user
// (`google_<id>`, a fresh sub) even when a password account with the same
// email already exists, so Alice clicks "Continue with Google" and finds an
// empty Humbugg. And the reverse: a Google-first Alice can never sign up with a
// password, because the email is taken by a user she cannot reset.
//
// So on `PreSignUp_ExternalProvider` this links the federated identity onto a
// NATIVE user — the one already there, or one created here on the spot with a
// random permanent password and a verified email. The native user is always the
// canonical sub; the social identity is an alias of it. Password recovery
// therefore works for everyone, which is why the password is set PERMANENT:
// `AdminCreateUser` alone leaves FORCE_CHANGE_PASSWORD, a state forgot-password
// refuses to act on.
//
// It is a zip Terraform packages straight from this file, no build, no ECR —
// `infra/modules/auth` — importing only the Cognito client the Node runtime
// ships. Native sign-ups (`PreSignUp_SignUp`) pass through untouched.
//
// **Linking by email is a trust decision, recorded here.** Whoever the IdP says
// owns alice@example.com gets Alice's Humbugg. That is the same trust every
// email-based password reset already extends, and every provider wired in
// verifies the address before returning it — Google, Apple and LinkedIn also
// SAY so in `email_verified`, and an explicit `false` from one of THOSE refuses
// the link below. Only those: Cognito hands every federated user an
// `email_verified` of `false` as a placeholder when the claim is not mapped,
// which is what Facebook's looks like — Facebook has no such claim and returns
// only confirmed addresses. Terraform maps the claim for the three that have it
// and names them in HUMBUGG_EMAIL_VERIFIED_PROVIDERS; the first live Google
// sign-in was refused before that distinction existed.
import { randomBytes } from 'node:crypto';

const EXTERNAL_PROVIDER = 'PreSignUp_ExternalProvider';

// The pool's identity providers by name, as Terraform declared them
// (`Google`, `Facebook`, `SignInWithApple`, `LinkedIn`). Cognito spells a
// federated username `<provider lowercased>_<id>`, and `AdminLinkProviderForUser`
// wants the name back in its declared case, so this is the lookup between them.
function providerNames(variable = 'HUMBUGG_IDENTITY_PROVIDERS') {
  return (process.env[variable] ?? '')
    .split(',')
    .map((name) => name.trim())
    .filter(Boolean);
}

/** Providers whose `email_verified` attribute is their own claim, not Cognito's placeholder. */
function emailVerifiedProviderNames() {
  return providerNames('HUMBUGG_EMAIL_VERIFIED_PROVIDERS');
}

/**
 * `google_1234` → `{ providerName: 'Google', providerUserId: '1234' }`.
 * Split at the FIRST underscore only: an Apple id has dots, a LinkedIn id is
 * opaque, and neither is promised to be underscore-free.
 *
 * **The id half is a fallback, not the truth.** The pool is case-insensitive,
 * so Cognito LOWERCASES this username before the trigger sees it, and a
 * LinkedIn `sub` is mixed-case: a link made from the username named an id
 * LinkedIn never issued, and every sign-in after failed "Invalid
 * ProviderName/Username combination". Terraform maps each provider's `sub`
 * into `custom:idp_sub` verbatim; the handler links with that when present.
 */
export function parseFederatedUsername(userName, names = providerNames()) {
  const separator = userName.indexOf('_');
  if (separator <= 0) return null;
  const prefix = userName.slice(0, separator).toLowerCase();
  const providerName = names.find((name) => name.toLowerCase() === prefix);
  if (!providerName) return null;
  return { providerName, providerUserId: userName.slice(separator + 1) };
}

// Cognito accepts what it is handed for an attribute value; the pool compares
// emails case-insensitively but stores the casing it was given. Lowercase
// before storing AND before searching, so the two ever agree.
function normaliseEmail(email) {
  return email.trim().toLowerCase();
}

// Length over charset (the pool's own policy says the same) and never seen by
// anyone: the user resets it through forgot-password if they ever want one.
// Base64 of 36 bytes is 48 characters with upper, lower and digits, which the
// policy's composition rules want; the two literal characters guarantee it.
function randomPermanentPassword() {
  return `${randomBytes(36).toString('base64')}Aa1`;
}

function attribute(attributes, name) {
  const value = attributes?.[name];
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

/** Native users only: a federated user's own record is never a link target. */
function nativeUser(users) {
  return users.find((user) => user.UserStatus !== 'EXTERNAL_PROVIDER');
}

/**
 * The six calls this makes, as one object, so the test beside this file can
 * hand in a fake and the SDK is never imported outside the Lambda runtime —
 * `node --test` runs it from a checkout with nothing installed.
 */
async function sdkCognito() {
  const sdk = await import('@aws-sdk/client-cognito-identity-provider');
  const client = new sdk.CognitoIdentityProviderClient({});
  const call = (Command) => (input) => client.send(new Command(input));
  return {
    listUsers: call(sdk.ListUsersCommand),
    adminConfirmSignUp: call(sdk.AdminConfirmSignUpCommand),
    adminUpdateUserAttributes: call(sdk.AdminUpdateUserAttributesCommand),
    adminCreateUser: call(sdk.AdminCreateUserCommand),
    adminSetUserPassword: call(sdk.AdminSetUserPasswordCommand),
    adminLinkProviderForUser: call(sdk.AdminLinkProviderForUserCommand),
  };
}

export function createHandler(cognito) {
  return async function handler(event) {
    if (event.triggerSource !== EXTERNAL_PROVIDER) return event;

    const attributes = event.request?.userAttributes ?? {};
    const rawEmail = attribute(attributes, 'email');
    if (!rawEmail) {
      // The pool requires an email and Humbugg reads a verified one back for
      // every send, so an identity without one has nothing to become.
      throw new Error('Your account with that provider has no email address. Sign in another way.');
    }
    const federated = parseFederatedUsername(event.userName);
    if (!federated) {
      throw new Error(`Unrecognised federated username "${event.userName}"`);
    }
    if (
      emailVerifiedProviderNames().includes(federated.providerName) &&
      attribute(attributes, 'email_verified') === 'false'
    ) {
      throw new Error('That provider has not verified your email address. Sign in another way.');
    }

    const providerUserId = attribute(attributes, 'custom:idp_sub') ?? federated.providerUserId;

    const email = normaliseEmail(rawEmail);
    const userPoolId = event.userPoolId;
    const givenName = attribute(attributes, 'given_name');
    const familyName = attribute(attributes, 'family_name');

    const listed = await cognito.listUsers({
      UserPoolId: userPoolId,
      Filter: `email = "${email}"`,
      Limit: 10,
    });
    const existing = nativeUser(listed.Users ?? []);
    let user = existing;

    if (user) {
      // A password account that was never confirmed, or whose email was never
      // verified, is confirmed and verified now on the provider's word — the
      // same word that just authenticated this sign-in.
      if (user.UserStatus === 'UNCONFIRMED') {
        await cognito.adminConfirmSignUp({ UserPoolId: userPoolId, Username: user.Username });
      }
      const verified = user.Attributes?.find((a) => a.Name === 'email_verified')?.Value;
      if (verified !== 'true') {
        await cognito.adminUpdateUserAttributes({
          UserPoolId: userPoolId,
          Username: user.Username,
          UserAttributes: [{ Name: 'email_verified', Value: 'true' }],
        });
      }
    } else {
      const created = await cognito.adminCreateUser({
        UserPoolId: userPoolId,
        Username: email,
        // SUPPRESS: no invitation mail. The person is on the sign-in page
        // right now; the account they are creating is this one.
        MessageAction: 'SUPPRESS',
        UserAttributes: [
          { Name: 'email', Value: email },
          { Name: 'email_verified', Value: 'true' },
          ...(givenName ? [{ Name: 'given_name', Value: givenName }] : []),
          ...(familyName ? [{ Name: 'family_name', Value: familyName }] : []),
        ],
      });
      user = created.User;
      await cognito.adminSetUserPassword({
        UserPoolId: userPoolId,
        Username: user.Username,
        Password: randomPermanentPassword(),
        Permanent: true,
      });
    }

    await cognito.adminLinkProviderForUser({
      UserPoolId: userPoolId,
      DestinationUser: { ProviderName: 'Cognito', ProviderAttributeValue: user.Username },
      SourceUser: {
        ProviderName: federated.providerName,
        ProviderAttributeName: 'Cognito_Subject',
        ProviderAttributeValue: providerUserId,
      },
    });

    console.log(
      JSON.stringify({
        message: 'linked federated identity to native user',
        provider: federated.providerName,
        // The sub, never the email: this log group is read casually.
        nativeUser: user.Username,
        createdNativeUser: !existing,
        // Whether the mapped sub was there, and whether the username's copy
        // would have been wrong — the LinkedIn finding, kept visible.
        subjectFromAttribute: Boolean(attribute(attributes, 'custom:idp_sub')),
        usernameSubjectDiffers: providerUserId !== federated.providerUserId,
      }),
    );

    return event;
  };
}

let runtimeHandler;
export async function handler(event) {
  runtimeHandler ??= createHandler(await sdkCognito());
  return runtimeHandler(event);
}
