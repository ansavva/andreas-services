// Rewritten from the web app's `AuthPage.test.tsx` against React Native queries.
//
// The behaviour under test is the same — consent gates account creation, the
// password confirmation must match, the reveal toggle flips the field, and a
// freshly-registered account goes to profile setup rather than a stale
// destination. What changed is how you reach a control: there is no DOM, so
// everything is found by accessibility label or role, and `fireEvent.changeText`
// replaces a `change` event on an `<input>`.
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

const mocks = {
  replace: jest.fn(),
  push: jest.fn(),
  register: jest.fn(),
  login: jest.fn(),
};

jest.mock('expo-router', () => ({
  useRouter: () => ({ replace: mocks.replace, push: mocks.push }),
  Link: ({ children }: { children?: React.ReactNode }) => children,
}));

jest.mock('../context/auth-context', () => ({
  useAuth: () => ({ register: mocks.register, login: mocks.login, authenticated: false }),
}));

// The Shell drags in the profile context and the account menu, neither of which
// this screen is about.
jest.mock('../components/shell', () => {
  const { View } = require('react-native');
  return {
    Shell: ({ children }: { children?: React.ReactNode }) => <View>{children}</View>,
    Card: ({ children }: { children?: React.ReactNode }) => <View>{children}</View>,
    LoadingPanel: ({ children }: { children?: React.ReactNode }) => <View>{children}</View>,
  };
});

import AuthScreen from './auth';
import { sessionKeys, sessionStore } from '../utils/session-store';

function fillCredentials({ confirm = true }: { confirm?: boolean } = {}) {
  fireEvent.changeText(screen.getByLabelText('Email address'), 'alex@example.com');
  fireEvent.changeText(screen.getByLabelText('Password'), 'Password1');
  if (confirm) fireEvent.changeText(screen.getByLabelText('Confirm password'), 'Password1');
}

beforeEach(() => {
  jest.clearAllMocks();
  mocks.register.mockResolvedValue(undefined);
  mocks.login.mockResolvedValue(undefined);
  Object.values(sessionKeys).forEach((key) => {
    if (typeof key === 'string') sessionStore.remove(key);
  });
});

describe('signup consent', () => {
  it('renders an unchecked-by-default consent checkbox', () => {
    render(<AuthScreen mode="signup" />);
    const checkbox = screen.getByLabelText('Agree to the Terms of Service and Privacy Policy');
    expect(checkbox.props.accessibilityState.checked).toBe(false);
  });

  it('blocks account creation and explains why when consent is not given', async () => {
    render(<AuthScreen mode="signup" />);
    fillCredentials();
    fireEvent.press(screen.getByText('Create account'));

    await waitFor(() =>
      expect(screen.getByText(/agree to the Terms of Service and Privacy Policy/i)).toBeOnTheScreen(),
    );
    expect(mocks.register).not.toHaveBeenCalled();
  });

  it('registers and records consent once the box is ticked', async () => {
    render(<AuthScreen mode="signup" />);
    fillCredentials();
    fireEvent.press(screen.getByLabelText('Agree to the Terms of Service and Privacy Policy'));
    fireEvent.press(screen.getByText('Create account'));

    await waitFor(() => expect(mocks.register).toHaveBeenCalledWith('alex@example.com', 'Password1'));
    const stashed = JSON.parse(sessionStore.get(sessionKeys.consent) ?? '{}');
    expect(stashed.version).toBeTruthy();
    // A valid UTC ISO-8601 timestamp round-trips through Date unchanged.
    expect(new Date(stashed.accepted_at).toISOString()).toBe(stashed.accepted_at);
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith('/confirm'));
  });

  it('requires matching password confirmation before registering', async () => {
    render(<AuthScreen mode="signup" />);
    fillCredentials({ confirm: false });
    fireEvent.changeText(screen.getByLabelText('Confirm password'), 'Different1');
    fireEvent.press(screen.getByLabelText('Agree to the Terms of Service and Privacy Policy'));
    fireEvent.press(screen.getByText('Create account'));

    await waitFor(() => expect(screen.getByText('Passwords must match.')).toBeOnTheScreen());
    expect(mocks.register).not.toHaveBeenCalled();
  });
});

describe('password visibility', () => {
  it('reveals and hides the login password', () => {
    render(<AuthScreen mode="login" />);
    // The native leaf drives masking from `secureTextEntry`, which is what the
    // reveal toggle flips — there is no `type` attribute to assert on.
    expect(screen.getByLabelText('Password').props.secureTextEntry).toBe(true);

    fireEvent.press(screen.getByLabelText('Show password'));
    expect(screen.getByLabelText('Password').props.secureTextEntry).toBe(false);

    fireEvent.press(screen.getByLabelText('Hide password'));
    expect(screen.getByLabelText('Password').props.secureTextEntry).toBe(true);
  });
});

describe('login routing', () => {
  it('sends a newly registered account to profile setup, not a stale destination', async () => {
    sessionStore.set(sessionKeys.consent, JSON.stringify({ version: 'test', accepted_at: new Date().toISOString() }));
    sessionStore.set(sessionKeys.returnTo, '/settings');
    render(<AuthScreen mode="login" />);
    fillCredentials({ confirm: false });

    fireEvent.press(screen.getByText('Sign in'));

    await waitFor(() => expect(mocks.login).toHaveBeenCalledWith('alex@example.com', 'Password1'));
    expect(mocks.replace).toHaveBeenCalledWith('/');
    expect(sessionStore.get(sessionKeys.returnTo)).toBeNull();
  });

  it('uses and clears a protected destination for an existing account', async () => {
    sessionStore.set(sessionKeys.returnTo, '/settings');
    render(<AuthScreen mode="login" />);
    fillCredentials({ confirm: false });

    fireEvent.press(screen.getByText('Sign in'));

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith('/settings'));
    expect(sessionStore.get(sessionKeys.returnTo)).toBeNull();
  });
});
