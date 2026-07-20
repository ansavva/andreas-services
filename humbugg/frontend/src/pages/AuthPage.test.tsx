// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  register: vi.fn().mockResolvedValue(undefined),
  login: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@ansavva/design-system', () => ({
  Button: ({ children, ...props }: Record<string, unknown> & { children?: unknown }) => (
    <button {...(props as Record<string, unknown>)}>{children as never}</button>
  ),
  Input: (props: Record<string, unknown>) => <input {...(props as Record<string, unknown>)} />,
}));

vi.mock('react-router', () => ({
  useNavigate: () => mocks.navigate,
  Link: ({ children, to, ...props }: Record<string, unknown> & { children?: unknown; to?: unknown }) => (
    <a href={typeof to === 'string' ? to : '#'} {...(props as Record<string, unknown>)}>{children as never}</a>
  ),
}));

vi.mock('../components/Layout', () => ({
  Shell: ({ children }: { children?: unknown }) => <div>{children as never}</div>,
  Card: ({ children }: { children?: unknown }) => <div>{children as never}</div>,
  StatusMessage: ({ message }: { message?: string | null }) => (message ? <p role="alert">{message}</p> : null),
}));

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ register: mocks.register, login: mocks.login }),
}));

import AuthPage from './AuthPage';

function fillCredentials() {
  fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'alex@example.com' } });
  fireEvent.change(screen.getByLabelText(/^password/i), { target: { value: 'Password1' } });
  const confirmation = screen.queryByLabelText(/confirm password/i, { selector: 'input' });
  if (confirmation) fireEvent.change(confirmation, { target: { value: 'Password1' } });
}

describe('AuthPage signup consent', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.register.mockResolvedValue(undefined);
    sessionStorage.clear();
  });

  afterEach(() => cleanup());

  it('renders an unchecked-by-default consent checkbox instead of the old passive sentence', () => {
    render(<AuthPage mode="signup" />);
    const checkbox = screen.getByRole('checkbox') as HTMLInputElement;
    expect(checkbox.checked).toBe(false);
    expect(screen.queryByText(/By creating an account, you agree/i)).not.toBeInTheDocument();
  });

  it('blocks account creation and shows a validation message when consent is not given', async () => {
    render(<AuthPage mode="signup" />);
    fillCredentials();
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/agree to the Terms of Service and Privacy Policy/i));
    expect(mocks.register).not.toHaveBeenCalled();
  });

  it('registers and records consent (version + UTC timestamp) once the box is ticked', async () => {
    render(<AuthPage mode="signup" />);
    fillCredentials();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() => expect(mocks.register).toHaveBeenCalledWith('alex@example.com', 'Password1'));
    const stashed = JSON.parse(sessionStorage.getItem('humbugg:consent') ?? '{}');
    expect(stashed.version).toBeTruthy();
    expect(new Date(stashed.accepted_at).toISOString()).toBe(stashed.accepted_at); // valid UTC ISO-8601
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith('/confirm'));
  });

  it('requires matching password confirmation before registering', async () => {
    render(<AuthPage mode="signup" />);
    fillCredentials();
    fireEvent.change(screen.getByLabelText(/confirm password/i, { selector: 'input' }), { target: { value: 'Different1' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Passwords must match.'));
    expect(mocks.register).not.toHaveBeenCalled();
  });

  it('lets the user reveal and hide both password entries', () => {
    render(<AuthPage mode="signup" />);
    const password = screen.getByLabelText(/^password/i) as HTMLInputElement;
    const confirmation = screen.getByLabelText(/confirm password/i, { selector: 'input' }) as HTMLInputElement;

    expect(password).toHaveAttribute('type', 'password');
    expect(confirmation).toHaveAttribute('type', 'password');
    fireEvent.click(screen.getByRole('button', { name: /show password/i }));
    fireEvent.click(screen.getByRole('button', { name: /show confirm password/i }));
    expect(password).toHaveAttribute('type', 'text');
    expect(confirmation).toHaveAttribute('type', 'text');
    fireEvent.click(screen.getByRole('button', { name: /hide password/i }));
    fireEvent.click(screen.getByRole('button', { name: /hide confirm password/i }));
    expect(password).toHaveAttribute('type', 'password');
    expect(confirmation).toHaveAttribute('type', 'password');
  });
});

describe('AuthPage password visibility', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  afterEach(() => cleanup());

  it('lets the user reveal their login password', () => {
    render(<AuthPage mode="login" />);
    const password = screen.getByLabelText(/^password/i) as HTMLInputElement;

    fireEvent.click(screen.getByRole('button', { name: /show password/i }));
    expect(password).toHaveAttribute('type', 'text');
  });
});

describe('AuthPage login routing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.login.mockResolvedValue(undefined);
    sessionStorage.clear();
  });

  afterEach(() => cleanup());

  it('sends a newly registered account to profile setup instead of a stale protected destination', async () => {
    sessionStorage.setItem('humbugg:consent', JSON.stringify({ version: 'test', accepted_at: new Date().toISOString() }));
    sessionStorage.setItem('humbugg:returnTo', '/app/settings');
    render(<AuthPage mode="login" />);
    fillCredentials();

    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(mocks.login).toHaveBeenCalledWith('alex@example.com', 'Password1'));
    expect(mocks.navigate).toHaveBeenCalledWith('/app');
    expect(sessionStorage.getItem('humbugg:returnTo')).toBeNull();
  });

  it('uses and clears a protected destination for an existing account', async () => {
    sessionStorage.setItem('humbugg:returnTo', '/app/settings');
    render(<AuthPage mode="login" />);
    fillCredentials();

    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith('/app/settings'));
    expect(sessionStorage.getItem('humbugg:returnTo')).toBeNull();
  });
});
