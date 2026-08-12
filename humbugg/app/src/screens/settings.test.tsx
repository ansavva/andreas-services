// Rewritten from the web app's `SettingsPage.test.tsx` against RN queries.
//
// The delete-account confirmation is the interesting half: it moved from a
// hand-rolled overlay to the design system's `AlertDialog`, so these assertions
// are what prove the guard survived the swap — the destructive button stays
// disabled until the typed name matches exactly.
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

const profile = {
  user_id: 'u',
  display_name: 'Alex Rivera',
  created_at: '',
  updated_at: '',
  non_essential_emails_enabled: false,
};

const mocks = {
  replace: jest.fn(),
  saveMe: jest.fn(),
  deleteAccount: jest.fn(),
  logout: jest.fn(),
  setProfile: jest.fn(),
};

jest.mock('expo-router', () => ({
  useRouter: () => ({ replace: mocks.replace, push: jest.fn() }),
  Link: ({ children }: { children?: React.ReactNode }) => children,
}));

jest.mock('../api/client', () => ({
  api: {
    saveMe: (...args: unknown[]) => mocks.saveMe(...args),
    deleteAccount: (...args: unknown[]) => mocks.deleteAccount(...args),
  },
  ApiError: class extends Error {},
}));

jest.mock('../context/auth-context', () => ({
  useAuth: () => ({
    accessToken: () => Promise.resolve('token'),
    email: 'alex@example.com',
    logout: mocks.logout,
    authenticated: true,
  }),
}));

jest.mock('../context/profile-context', () => ({
  useProfile: () => ({
    profile,
    loading: false,
    loaded: true,
    error: null,
    setProfile: mocks.setProfile,
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

import SettingsScreen from './settings';

beforeEach(() => {
  jest.clearAllMocks();
  mocks.saveMe.mockResolvedValue(profile);
  mocks.deleteAccount.mockResolvedValue(undefined);
  mocks.logout.mockResolvedValue(undefined);
});

describe('display name', () => {
  it('prefills the current display name', () => {
    render(<SettingsScreen />);
    expect(screen.getByLabelText('Display name').props.value).toBe('Alex Rivera');
  });

  it('refuses to save an empty name', async () => {
    render(<SettingsScreen />);
    fireEvent.changeText(screen.getByLabelText('Display name'), '   ');
    fireEvent.press(screen.getByText('Save changes'));

    await waitFor(() => expect(screen.getByText('Enter the name your groups should see.')).toBeOnTheScreen());
    expect(mocks.saveMe).not.toHaveBeenCalled();
  });

  it('saves a trimmed name and confirms it', async () => {
    render(<SettingsScreen />);
    fireEvent.changeText(screen.getByLabelText('Display name'), '  Maya Lin  ');
    fireEvent.press(screen.getByText('Save changes'));

    await waitFor(() => expect(mocks.saveMe).toHaveBeenCalledWith('token', 'Maya Lin'));
    await waitFor(() => expect(screen.getByText('Display name saved.')).toBeOnTheScreen());
  });
});

describe('email preference', () => {
  it('sends the display name alongside the preference so the PUT validates', async () => {
    render(<SettingsScreen />);
    fireEvent.press(screen.getByLabelText('Send me non-essential emails'));

    await waitFor(() => expect(mocks.saveMe).toHaveBeenCalledWith('token', 'Alex Rivera', true));
    await waitFor(() => expect(screen.getByText('Non-essential emails turned on.')).toBeOnTheScreen());
  });
});

describe('account deletion', () => {
  it('keeps the destructive action disabled until the typed name matches exactly', async () => {
    render(<SettingsScreen />);
    fireEvent.press(screen.getByText('Delete my account…'));

    await waitFor(() => expect(screen.getByText('Delete your account permanently?')).toBeOnTheScreen());

    fireEvent.press(screen.getByText('Permanently delete'));
    expect(mocks.deleteAccount).not.toHaveBeenCalled();

    fireEvent.changeText(screen.getByLabelText('Confirm your display name'), 'Alex');
    fireEvent.press(screen.getByText('Permanently delete'));
    expect(mocks.deleteAccount).not.toHaveBeenCalled();

    fireEvent.changeText(screen.getByLabelText('Confirm your display name'), 'Alex Rivera');
    fireEvent.press(screen.getByText('Permanently delete'));
    await waitFor(() => expect(mocks.deleteAccount).toHaveBeenCalledWith('token'));
  });

  it('ends the session after deleting, so the erased account cannot keep acting', async () => {
    render(<SettingsScreen />);
    fireEvent.press(screen.getByText('Delete my account…'));
    await waitFor(() => screen.getByLabelText('Confirm your display name'));
    fireEvent.changeText(screen.getByLabelText('Confirm your display name'), 'Alex Rivera');
    fireEvent.press(screen.getByText('Permanently delete'));

    await waitFor(() => expect(mocks.logout).toHaveBeenCalled());
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith('/login'));
  });
});
