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
});
