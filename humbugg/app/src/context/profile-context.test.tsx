// The profile contract the protected layout leans on: `loaded && !profile` is the
// "brand-new user, show the setup form" state, so a 404 from /me must resolve to it —
// and only a 404. Any other failure is an error, and signing out resets everything.
import { render, screen, waitFor } from '@testing-library/react-native';
import { Text } from 'react-native';

const mocks = {
  authenticated: true,
};

const mockGetMe = jest.fn();

jest.mock('../api/client', () => {
  const actual = jest.requireActual('../api/client');
  return {
    ApiError: actual.ApiError,
    api: { getMe: (...args: unknown[]) => mockGetMe(...args) },
  };
});

// One stable object: the provider's reload callback depends on the auth value, so a
// mock returning a fresh object every render would loop the fetch effect forever.
const mockAuth = {
  get authenticated() {
    return mocks.authenticated;
  },
  accessToken: async () => 'test-token',
};

jest.mock('./auth-context', () => ({
  useAuth: () => mockAuth,
}));

import { ApiError } from '../api/client';
import { ProfileProvider, useProfile } from './profile-context';

function Probe() {
  const { profile, loaded, error } = useProfile();
  if (error) return <Text>{`error: ${error}`}</Text>;
  if (!loaded) return <Text>loading</Text>;
  return <Text>{profile ? `profile: ${profile.display_name}` : 'needs setup'}</Text>;
}

function renderProbe() {
  return render(
    <ProfileProvider>
      <Probe />
    </ProfileProvider>,
  );
}

describe('ProfileProvider', () => {
  beforeEach(() => {
    mocks.authenticated = true;
    mockGetMe.mockReset();
  });

  it('loads the signed-in profile once', async () => {
    mockGetMe.mockResolvedValue({ display_name: 'Alice' });
    renderProbe();
    await waitFor(() => expect(screen.getByText('profile: Alice')).toBeTruthy());
    expect(mockGetMe).toHaveBeenCalledTimes(1);
    expect(mockGetMe).toHaveBeenCalledWith('test-token');
  });

  it('treats a 404 as "needs setup", not as an error', async () => {
    mockGetMe.mockRejectedValue(new ApiError(404, 'not_found', 'No profile yet.'));
    renderProbe();
    await waitFor(() => expect(screen.getByText('needs setup')).toBeTruthy());
  });

  it('surfaces any other failure as an error', async () => {
    mockGetMe.mockRejectedValue(new ApiError(500, 'internal_error', 'It broke.'));
    renderProbe();
    await waitFor(() => expect(screen.getByText('error: It broke.')).toBeTruthy());
  });

  it('never fetches while signed out', async () => {
    mocks.authenticated = false;
    renderProbe();
    // Signed out is "not loaded" — the protected layout holds on that, and no
    // request goes out with no token to send.
    await waitFor(() => expect(screen.getByText('loading')).toBeTruthy());
    expect(mockGetMe).not.toHaveBeenCalled();
  });
});
