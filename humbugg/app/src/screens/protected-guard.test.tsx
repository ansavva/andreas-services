// Rewritten from the web app's `ProtectedRoute.test.tsx`. Same three states,
// asserted against the group layout that replaced the wrapper component.
import { render, screen } from '@testing-library/react-native';

const mocks = {
  auth: { loading: false, authenticated: false },
  profileLoaded: false,
  pathname: '/settings',
};

jest.mock('expo-router', () => {
  const { Text } = require('react-native');
  return {
    Redirect: ({ href }: { href: string }) => <Text>{`redirect:${href}`}</Text>,
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
});

it('holds while the session is still being restored, rather than bouncing to login', () => {
  mocks.auth = { loading: true, authenticated: false };
  render(<ProtectedLayout />);
  expect(screen.getByText('Checking your session…')).toBeOnTheScreen();
  expect(screen.queryByText('redirect:/login')).toBeNull();
});

it('redirects a signed-out visitor to login', () => {
  mocks.auth = { loading: false, authenticated: false };
  render(<ProtectedLayout />);
  expect(screen.getByText('redirect:/login')).toBeOnTheScreen();
});

it('remembers where the visitor was headed, so signing in returns them there', () => {
  mocks.auth = { loading: false, authenticated: false };
  mocks.pathname = '/groups/g1';
  render(<ProtectedLayout />);
  expect(sessionStore.get(sessionKeys.returnTo)).toBe('/groups/g1');
});

it('holds while the profile loads, so a first-run account is not judged missing', () => {
  mocks.auth = { loading: false, authenticated: true };
  mocks.profileLoaded = false;
  render(<ProtectedLayout />);
  expect(screen.getByText('Loading your profile…')).toBeOnTheScreen();
});

it('renders the protected stack once the session and profile have settled', () => {
  mocks.auth = { loading: false, authenticated: true };
  mocks.profileLoaded = true;
  render(<ProtectedLayout />);
  expect(screen.getByText('protected content')).toBeOnTheScreen();
});
