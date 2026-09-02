// The invitation screen. `utils/invite.test.ts` covers parsing the fragment;
// this covers what the screen does with it — because an invite link that has
// already been emailed cannot be re-issued if this breaks.
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

const mocks = {
  replace: jest.fn(),
  push: jest.fn(),
  joinGroup: jest.fn(),
  getInvitation: jest.fn(),
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

jest.mock('../api/client', () => {
  // A real status, because the screen maps status codes to the words a person following a link can
  // act on — a bare Error would make every refusal look the same, which is the bug under test.
  class ApiError extends Error {
    status: number;
    constructor(status: number, _code: string, message: string) {
      super(message);
      this.status = status;
    }
  }
  return {
    api: {
      joinGroup: (...args: unknown[]) => mocks.joinGroup(...args),
      getInvitation: (...args: unknown[]) => mocks.getInvitation(...args),
    },
    ApiError,
  };
});

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
  mocks.getInvitation.mockResolvedValue({
    group_id: 'g1',
    exchange_name: 'Office Exchange',
    customization: {},
  });
});

const { ApiError } = jest.requireMock('../api/client') as {
  ApiError: new (status: number, code: string, message: string) => Error;
};

it('reads the secret out of the deep link and joins with it', async () => {
  mocks.initialUrl = 'humbugg://join/g1#invite=s3cr3t';
  render(<JoinScreen groupId="g1" />);

  await waitFor(() => expect(sessionStore.get(sessionKeys.join('g1'))).toBe('s3cr3t'));
  fireEvent.press(screen.getByText('Join the exchange'));

  await waitFor(() => expect(mocks.joinGroup).toHaveBeenCalledWith('token', 'g1', 's3cr3t'));
  await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith('/groups/g1'));
});

it('survives the sign-in round trip by reading the stashed secret', async () => {
  // No fragment on this visit — the app came back from /login, where the
  // fragment did not follow.
  sessionStore.set(sessionKeys.join('g1'), 'stashed-secret');
  render(<JoinScreen groupId="g1" />);

  fireEvent.press(screen.getByText('Join the exchange'));
  await waitFor(() => expect(mocks.joinGroup).toHaveBeenCalledWith('token', 'g1', 'stashed-secret'));
});

it('says so when the link carried no secret, and offers nothing to press', async () => {
  render(<JoinScreen groupId="g1" />);
  await waitFor(() =>
    expect(screen.getByText(/This invitation link is incomplete/)).toBeOnTheScreen(),
  );
  fireEvent.press(screen.getByText('Join the exchange'));
  expect(mocks.joinGroup).not.toHaveBeenCalled();
});

it('remembers the invitation as the return destination for a signed-out visitor', async () => {
  mocks.authenticated = false;
  render(<JoinScreen groupId="g1" />);
  await waitFor(() => expect(sessionStore.get(sessionKeys.returnTo)).toBe('/join/g1'));
  expect(screen.getByText('Sign in or create an account')).toBeOnTheScreen();
});

/**
 * The exchange is named before anybody is asked to join it (#134).
 *
 * The preview endpoint existed the whole time and nothing called it — and it would not have worked
 * if it had, because it fetched a relative `/api` path that stopped resolving when the app moved to
 * its own origin.
 */
it('names the exchange the invitation is for', async () => {
  mocks.initialUrl = 'humbugg://join/g1#invite=s3cr3t';
  render(<JoinScreen groupId="g1" />);

  await waitFor(() => expect(screen.getByText('Office Exchange')).toBeOnTheScreen());
  expect(mocks.getInvitation).toHaveBeenCalledWith('g1', 's3cr3t');
});

/** A preview that fails costs the name and nothing else — the join still gives the real answer. */
it('still offers to join when the preview cannot be loaded', async () => {
  mocks.initialUrl = 'humbugg://join/g1#invite=s3cr3t';
  mocks.getInvitation.mockRejectedValue(new ApiError(403, 'forbidden', 'nope'));
  render(<JoinScreen groupId="g1" />);

  await waitFor(() => expect(sessionStore.get(sessionKeys.join('g1'))).toBe('s3cr3t'));
  expect(screen.getByText('Join this Secret Santa exchange')).toBeOnTheScreen();
  expect(screen.queryByText('nope')).toBeNull();
});

it('tells a signed-out visitor they will need an account before they press anything', async () => {
  mocks.authenticated = false;
  render(<JoinScreen groupId="g1" />);

  expect(screen.getByText(/You need a free Humbugg account/)).toBeOnTheScreen();
  expect(screen.getByText(/keeps your wishlist yours/)).toBeOnTheScreen();
});

/**
 * Each refusal says the thing that person can act on.
 *
 * The API's own messages are written for whoever the endpoint usually serves, which is mostly an
 * organizer. Somebody who just clicked a link in a group chat cannot reset a draw or buy Plus.
 */
describe('when joining is refused', () => {
  beforeEach(() => {
    mocks.initialUrl = 'humbugg://join/g1#invite=s3cr3t';
  });

  async function attempt(error: Error) {
    mocks.joinGroup.mockRejectedValue(error);
    render(<JoinScreen groupId="g1" />);
    await waitFor(() => expect(sessionStore.get(sessionKeys.join('g1'))).toBe('s3cr3t'));
    fireEvent.press(screen.getByText('Join the exchange'));
    await waitFor(() => expect(mocks.joinGroup).toHaveBeenCalled());
  }

  it('sends an invalid or rotated link to the organizer for a fresh one', async () => {
    await attempt(new ApiError(403, 'forbidden', 'This invitation is invalid or has expired.'));

    expect(screen.getByText(/ask them for the current one/)).toBeOnTheScreen();
  });

  it('says a full exchange is the organizer’s to fix, not the visitor’s', async () => {
    await attempt(new ApiError(402, 'plus_required', 'Plus is required for participant 7.'));

    expect(screen.getByText(/Only the organizer can make room/)).toBeOnTheScreen();
    // Never the API's own words here: they tell a non-member to buy Plus for an exchange they are
    // not in.
    expect(screen.queryByText(/Plus is required/)).toBeNull();
  });

  it('passes a drawn exchange’s own explanation straight through', async () => {
    await attempt(new ApiError(409, 'conflict', 'This exchange has already been drawn, so it is closed to new members.'));

    expect(screen.getByText(/closed to new members/)).toBeOnTheScreen();
  });
});
