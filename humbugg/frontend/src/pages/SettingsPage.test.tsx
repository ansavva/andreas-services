// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Shared mock handles, hoisted so the vi.mock factories below can safely reference them.
const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  logout: vi.fn().mockResolvedValue(undefined),
  accessToken: vi.fn().mockResolvedValue('access-token'),
  setProfile: vi.fn(),
  api: {
    saveMe: vi.fn(),
    uploadAvatar: vi.fn(),
    removeAvatar: vi.fn(),
    deleteAccount: vi.fn().mockResolvedValue(undefined),
  },
  profile: {
    user_id: 'u1',
    display_name: 'Alex Rivera',
    created_at: 'now',
    updated_at: 'now',
    avatar_url: null as string | null,
  },
}));

vi.mock('@ansavva/design-system', () => ({
  Button: ({ children, ...props }: Record<string, unknown> & { children?: unknown }) => (
    <button {...(props as Record<string, unknown>)}>{children as never}</button>
  ),
  Input: (props: Record<string, unknown>) => <input {...(props as Record<string, unknown>)} />,
  Textarea: (props: Record<string, unknown>) => <textarea {...(props as Record<string, unknown>)} />,
}));

vi.mock('react-router', () => ({
  useNavigate: () => mocks.navigate,
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
  Link: ({ children, to, ...props }: Record<string, unknown> & { children?: unknown; to?: unknown }) => (
    <a href={typeof to === 'string' ? to : '#'} {...(props as Record<string, unknown>)}>{children as never}</a>
  ),
}));

vi.mock('../api/client', () => ({ api: mocks.api, ApiError: class ApiError extends Error {} }));

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ authenticated: true, email: 'alex@example.com', logout: mocks.logout, accessToken: mocks.accessToken }),
}));

vi.mock('../context/ProfileContext', () => ({
  useProfile: () => ({
    profile: mocks.profile,
    loading: false,
    loaded: true,
    error: null,
    reload: vi.fn(),
    setProfile: mocks.setProfile,
  }),
}));

import SettingsPage from './SettingsPage';

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.accessToken.mockResolvedValue('access-token');
    mocks.logout.mockResolvedValue(undefined);
    mocks.api.deleteAccount.mockResolvedValue(undefined);
    mocks.api.saveMe.mockResolvedValue({ ...mocks.profile, display_name: 'Alex Newname' });
    mocks.api.removeAvatar.mockResolvedValue({ ...mocks.profile, avatar_url: null });
  });

  afterEach(() => cleanup());

  it('shows the account email as read-only', () => {
    render(<SettingsPage />);
    const email = screen.getByLabelText('Email') as HTMLInputElement;
    expect(email.value).toBe('alex@example.com');
    expect(email).toHaveAttribute('readonly');
  });

  it('saves an updated display name', async () => {
    render(<SettingsPage />);
    const nameField = screen.getByLabelText(/display name/i);
    fireEvent.change(nameField, { target: { value: 'Alex Newname' } });
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(mocks.api.saveMe).toHaveBeenCalledWith('access-token', 'Alex Newname'));
    await waitFor(() => expect(mocks.setProfile).toHaveBeenCalled());
  });

  it('keeps the delete button disabled until the typed name matches exactly', () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole('button', { name: /delete my account/i }));

    const confirmButton = screen.getByRole('button', { name: /permanently delete/i });
    expect(confirmButton).toBeDisabled();

    const confirmField = screen.getByLabelText('Confirm your display name');
    fireEvent.change(confirmField, { target: { value: 'Alex River' } });
    expect(confirmButton).toBeDisabled();

    fireEvent.change(confirmField, { target: { value: 'Alex Rivera' } });
    expect(confirmButton).toBeEnabled();
  });

  it('deletes the account, signs out, and returns to the marketing home on confirm', async () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole('button', { name: /delete my account/i }));
    fireEvent.change(screen.getByLabelText('Confirm your display name'), { target: { value: 'Alex Rivera' } });
    fireEvent.click(screen.getByRole('button', { name: /permanently delete/i }));

    await waitFor(() => expect(mocks.api.deleteAccount).toHaveBeenCalledWith('access-token'));
    await waitFor(() => expect(mocks.logout).toHaveBeenCalled());
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith('/?account_deleted=1'));
  });

  it('does not call delete when the name does not match', () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole('button', { name: /delete my account/i }));
    fireEvent.change(screen.getByLabelText('Confirm your display name'), { target: { value: 'someone else' } });
    fireEvent.click(screen.getByRole('button', { name: /permanently delete/i }));
    expect(mocks.api.deleteAccount).not.toHaveBeenCalled();
  });
});
