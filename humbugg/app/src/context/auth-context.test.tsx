// The restore-on-mount contract: a stored session settles into "signed in", a broken or
// absent one into "signed out", and — the documented trap — an UNCONFIGURED auth setup
// settles into signed-out instead of spinning forever (empty EXPO_PUBLIC_COGNITO_* values
// are a different code path, which is why the e2e export uses fake-but-present ones).
import { render, screen, waitFor } from '@testing-library/react-native';
import { Text } from 'react-native';

const mocks = {
  configured: true,
  tokens: null as { accessToken: string; refreshToken: string; idToken: string; expiresAt: number } | null,
  loadRejects: false,
};

const mockLoadTokens = jest.fn(async () => {
  if (mocks.loadRejects) throw new Error('storage exploded');
  return mocks.tokens;
});

jest.mock('../auth/oauth', () => ({
  get isAuthConfigured() {
    return mocks.configured;
  },
  loadTokens: () => mockLoadTokens(),
  emailFromIdToken: (idToken: string | null) => (idToken ? 'restored@humbugg.test' : null),
  currentAccessToken: jest.fn(),
  signInNative: jest.fn(),
  signOut: jest.fn(),
  startWebSignIn: jest.fn(),
}));

import { AuthProvider, useAuth } from './auth-context';

function Probe() {
  const auth = useAuth();
  if (auth.loading) return <Text>checking</Text>;
  return <Text>{auth.authenticated ? `in as ${auth.email}` : 'signed out'}</Text>;
}

function renderProbe() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
}

describe('AuthProvider restore-on-mount', () => {
  beforeEach(() => {
    mocks.configured = true;
    mocks.tokens = null;
    mocks.loadRejects = false;
    mockLoadTokens.mockClear();
  });

  it('adopts a stored session', async () => {
    mocks.tokens = {
      accessToken: 'a',
      refreshToken: 'r',
      idToken: 'i',
      expiresAt: Date.now() + 3_600_000,
    };
    renderProbe();
    await waitFor(() => expect(screen.getByText('in as restored@humbugg.test')).toBeTruthy());
  });

  it('settles signed out when nothing is stored', async () => {
    renderProbe();
    await waitFor(() => expect(screen.getByText('signed out')).toBeTruthy());
  });

  it('a broken token store means signed out, not a crash', async () => {
    mocks.loadRejects = true;
    renderProbe();
    await waitFor(() => expect(screen.getByText('signed out')).toBeTruthy());
  });

  it('unconfigured auth settles signed out without touching the store', async () => {
    mocks.configured = false;
    renderProbe();
    await waitFor(() => expect(screen.getByText('signed out')).toBeTruthy());
    expect(mockLoadTokens).not.toHaveBeenCalled();
  });
});
