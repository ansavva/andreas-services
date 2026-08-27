// The signed-out gate's one component: it starts the hosted flow on mount, and the only
// thing it ever renders for real is the failure — the retry has to live here because
// there is nowhere to redirect to when the hosted page is unreachable.
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

const mockLogin = jest.fn<Promise<void>, [string?]>();

// One stable object: the component's mount effect depends on the auth value, so a mock
// returning a fresh object per render would restart the flow on every render.
const mockAuth = { login: (...args: [string?]) => mockLogin(...args) };

jest.mock('../context/auth-context', () => ({
  useAuth: () => mockAuth,
}));

import { SignInRedirect } from './sign-in-redirect';

describe('SignInRedirect', () => {
  beforeEach(() => mockLogin.mockReset());

  it('starts the hosted flow on mount, carrying where the user was headed', async () => {
    mockLogin.mockResolvedValue(undefined);
    render(<SignInRedirect returnTo="/groups/g1" />);

    expect(screen.getByText('Taking you to sign in…')).toBeTruthy();
    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith('/groups/g1'));
  });

  it('shows the failure with a retry when the hosted page is unreachable', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Could not resolve auth.humbugg.com'));
    mockLogin.mockResolvedValueOnce(undefined);
    render(<SignInRedirect />);

    await waitFor(() => expect(screen.getByText('Could not resolve auth.humbugg.com')).toBeTruthy());

    fireEvent.press(screen.getByText('Try again'));
    await waitFor(() => expect(mockLogin).toHaveBeenCalledTimes(2));
    // A successful retry clears the failure back to the redirect holding state.
    await waitFor(() => expect(screen.getByText('Taking you to sign in…')).toBeTruthy());
  });
});
