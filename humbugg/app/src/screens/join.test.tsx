// The invitation screen. `utils/invite.test.ts` covers parsing the fragment;
// this covers what the screen does with it — because an invite link that has
// already been emailed cannot be re-issued if this breaks.
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

const mocks = {
  replace: jest.fn(),
  push: jest.fn(),
  joinGroup: jest.fn(),
  authenticated: true,
  initialUrl: null as string | null,
};

jest.mock('expo-router', () => ({
  useRouter: () => ({ replace: mocks.replace, push: mocks.push }),
  Link: ({ children }: { children?: React.ReactNode }) => children,
}));

jest.mock('expo-linking', () => ({
  getInitialURL: () => Promise.resolve(mocks.initialUrl),
  createURL: (path: string) => `humbugg://${path}`,
}));

jest.mock('../api/client', () => ({
  api: { joinGroup: (...args: unknown[]) => mocks.joinGroup(...args) },
  ApiError: class extends Error {},
}));

jest.mock('../context/auth-context', () => ({
  useAuth: () => ({
    accessToken: () => Promise.resolve('token'),
    authenticated: mocks.authenticated,
    email: 'alex@example.com',
  }),
}));

jest.mock('../components/shell', () => {
  const { View } = require('react-native');
  return {
    Shell: ({ children }: { children?: React.ReactNode }) => <View>{children}</View>,
    Card: ({ children }: { children?: React.ReactNode }) => <View>{children}</View>,
    LoadingPanel: ({ children }: { children?: React.ReactNode }) => <View>{children}</View>,
  };
});

import JoinScreen from './join';
import { sessionKeys, sessionStore } from '../utils/session-store';

beforeEach(() => {
  jest.clearAllMocks();
  mocks.authenticated = true;
  mocks.initialUrl = null;
  sessionStore.remove(sessionKeys.join('g1'));
  sessionStore.remove(sessionKeys.returnTo);
  mocks.joinGroup.mockResolvedValue({});
});

it('reads the secret out of the deep link and joins with it', async () => {
  mocks.initialUrl = 'humbugg://join/g1#invite=s3cr3t';
  render(<JoinScreen groupId="g1" />);

  await waitFor(() => expect(sessionStore.get(sessionKeys.join('g1'))).toBe('s3cr3t'));
  fireEvent.press(screen.getByText('Join the group'));

  await waitFor(() => expect(mocks.joinGroup).toHaveBeenCalledWith('token', 'g1', 's3cr3t'));
  await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith('/groups/g1'));
});

it('survives the sign-in round trip by reading the stashed secret', async () => {
  // No fragment on this visit — the app came back from /login, where the
  // fragment did not follow.
  sessionStore.set(sessionKeys.join('g1'), 'stashed-secret');
  render(<JoinScreen groupId="g1" />);

  fireEvent.press(screen.getByText('Join the group'));
  await waitFor(() => expect(mocks.joinGroup).toHaveBeenCalledWith('token', 'g1', 'stashed-secret'));
});

it('says so when the link carried no secret, and offers nothing to press', async () => {
  render(<JoinScreen groupId="g1" />);
  await waitFor(() =>
    expect(screen.getByText('This invitation link is incomplete or has expired.')).toBeOnTheScreen(),
  );
  fireEvent.press(screen.getByText('Join the group'));
  expect(mocks.joinGroup).not.toHaveBeenCalled();
});

it('remembers the invitation as the return destination for a signed-out visitor', async () => {
  mocks.authenticated = false;
  render(<JoinScreen groupId="g1" />);
  await waitFor(() => expect(sessionStore.get(sessionKeys.returnTo)).toBe('/join/g1'));
  expect(screen.getByText('Sign in or create an account')).toBeOnTheScreen();
});
