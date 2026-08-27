// Rewritten from the web app's `ProtectedRoute.test.tsx`. Same three states,
// asserted against the group layout that replaced the wrapper component.
import { render, screen, waitFor } from '@testing-library/react-native';

const login = jest.fn(async () => {});

const mocks = {
  auth: { loading: false, authenticated: false, login },
  profileLoaded: false,
  pathname: '/settings',
};

jest.mock('expo-router', () => {
  const { Text } = require('react-native');
  return {
    Stack: () => <Text>protected content</Text>,
    usePathname: () => mocks.pathname,
  };
});

jest.mock('../context/auth-context', () => ({ useAuth: () => mocks.auth }));
jest.mock('../context/profile-context', () => ({
  useProfile: () => ({ loaded: mocks.profileLoaded }),
}));

import ProtectedLayout from '../app/(protected)/_layout';
import { sessionKeys, sessionStore } from '../utils/session-store';

beforeEach(() => {
  sessionStore.remove(sessionKeys.returnTo);
  mocks.pathname = '/settings';
  login.mockClear();
});

it('holds while the session is still being restored, rather than leaving for the hosted page', () => {
  mocks.auth = { loading: true, authenticated: false, login };
  render(<ProtectedLayout />);
  expect(screen.getByText('Checking your session…')).toBeOnTheScreen();
  expect(login).not.toHaveBeenCalled();
});

// No interstitial: the guard starts the hosted flow itself rather than routing
// to a page with a button on it.
it('sends a signed-out visitor straight to the hosted sign-in page', async () => {
  mocks.auth = { loading: false, authenticated: false, login };
  render(<ProtectedLayout />);
  expect(screen.getByText('Taking you to sign in…')).toBeOnTheScreen();
  await waitFor(() => expect(login).toHaveBeenCalled());
});

it('carries where the visitor was headed, so signing in returns them there', async () => {
  mocks.auth = { loading: false, authenticated: false, login };
  mocks.pathname = '/groups/g1';
  render(<ProtectedLayout />);
  await waitFor(() => expect(login).toHaveBeenCalledWith('/groups/g1'));
});

it('holds while the profile loads, so a first-run account is not judged missing', () => {
  mocks.auth = { loading: false, authenticated: true, login };
  mocks.profileLoaded = false;
  render(<ProtectedLayout />);
  expect(screen.getByText('Loading your profile…')).toBeOnTheScreen();
});

it('renders the protected stack once the session and profile have settled', () => {
  mocks.auth = { loading: false, authenticated: true, login };
  mocks.profileLoaded = true;
  render(<ProtectedLayout />);
  expect(screen.getByText('protected content')).toBeOnTheScreen();
});
