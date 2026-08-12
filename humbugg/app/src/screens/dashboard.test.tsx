// Rewritten from the web app's `DashboardPage.test.tsx` against RN queries.
//
// The two behaviours worth pinning are both about the profile-less first run:
// a brand-new account gets the setup form instead of an empty group list, and
// the consent stashed at signup is what gets recorded when the profile row is
// finally created.
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

const mocks = {
  push: jest.fn(),
  replace: jest.fn(),
  listGroups: jest.fn(),
  saveMe: jest.fn(),
  uploadAvatar: jest.fn(),
  setProfile: jest.fn(),
  profile: null as unknown,
};

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mocks.push, replace: mocks.replace }),
  Link: ({ children }: { children?: React.ReactNode }) => children,
}));

jest.mock('../api/client', () => ({
  api: {
    listGroups: (...args: unknown[]) => mocks.listGroups(...args),
    saveMe: (...args: unknown[]) => mocks.saveMe(...args),
    uploadAvatar: (...args: unknown[]) => mocks.uploadAvatar(...args),
  },
  ApiError: class extends Error {},
}));

jest.mock('../context/auth-context', () => ({
  useAuth: () => ({
    accessToken: () => Promise.resolve('token'),
    email: 'alex@example.com',
    authenticated: true,
  }),
}));

jest.mock('../context/profile-context', () => ({
  useProfile: () => ({ profile: mocks.profile, loaded: true, setProfile: mocks.setProfile }),
}));

jest.mock('../components/shell', () => {
  const { View } = require('react-native');
  return {
    Shell: ({ children }: { children?: React.ReactNode }) => <View>{children}</View>,
    Card: ({ children }: { children?: React.ReactNode }) => <View>{children}</View>,
    LoadingPanel: ({ children }: { children?: React.ReactNode }) => <View>{children}</View>,
  };
});

import DashboardScreen from './dashboard';
import { sessionKeys, sessionStore } from '../utils/session-store';

beforeEach(() => {
  jest.clearAllMocks();
  mocks.listGroups.mockResolvedValue([]);
  sessionStore.remove(sessionKeys.consent);
});

describe('profile setup', () => {
  beforeEach(() => { mocks.profile = null; });

  it('asks a brand-new account for a display name instead of listing groups', async () => {
    render(<DashboardScreen />);
    await waitFor(() => expect(screen.getByText('What should your group call you?')).toBeOnTheScreen());
    expect(mocks.listGroups).not.toHaveBeenCalled();
  });

  it('refuses to save an empty display name', async () => {
    render(<DashboardScreen />);
    await waitFor(() => screen.getByText('Continue'));
    fireEvent.press(screen.getByText('Continue'));

    await waitFor(() => expect(screen.getByText('Enter the name your group should see.')).toBeOnTheScreen());
    expect(mocks.saveMe).not.toHaveBeenCalled();
  });

  it('records the consent stashed at signup when the profile row is created', async () => {
    const consent = { version: '2026.1', accepted_at: '2026-01-01T00:00:00.000Z' };
    sessionStore.set(sessionKeys.consent, JSON.stringify(consent));
    mocks.saveMe.mockResolvedValue({ user_id: 'u', display_name: 'Alex' });

    render(<DashboardScreen />);
    await waitFor(() => screen.getByLabelText('Display name'));
    fireEvent.changeText(screen.getByLabelText('Display name'), 'Alex');
    fireEvent.press(screen.getByText('Continue'));

    await waitFor(() => expect(mocks.saveMe).toHaveBeenCalledWith('token', 'Alex', false, consent));
    // The stash is one-shot: it must not be replayed onto a later save.
    await waitFor(() => expect(sessionStore.get(sessionKeys.consent)).toBeNull());
  });
});

describe('group list', () => {
  beforeEach(() => {
    mocks.profile = { user_id: 'u', display_name: 'Alex', non_essential_emails_enabled: false };
  });

  it('shows the empty state when there are no groups', async () => {
    render(<DashboardScreen />);
    await waitFor(() => expect(screen.getByText('No groups yet')).toBeOnTheScreen());
  });

  it('lists a group with its status', async () => {
    mocks.listGroups.mockResolvedValue([
      {
        group_id: 'g1',
        name: 'The Holly Jolly Crew',
        status: 'drawn',
        event_date: null,
        is_organizer: true,
        currency: 'USD',
        plan: 'free',
        participant_limit: 6,
        created_at: '',
        updated_at: '',
      },
    ]);

    render(<DashboardScreen />);
    await waitFor(() => expect(screen.getByText('The Holly Jolly Crew')).toBeOnTheScreen());
    expect(screen.getByText('Drawn')).toBeOnTheScreen();
    expect(screen.getByText(/Organizing/)).toBeOnTheScreen();
  });

  it('validates the create-group form before calling the API', async () => {
    render(<DashboardScreen />);
    await waitFor(() => screen.getByText('Create group'));
    fireEvent.press(screen.getByText('Create group'));

    await waitFor(() => expect(screen.getByText('Enter a group name.')).toBeOnTheScreen());
  });
});
