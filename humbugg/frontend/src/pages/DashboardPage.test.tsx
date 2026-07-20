// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';

const mocks = vi.hoisted(() => ({
  accessToken: vi.fn().mockResolvedValue('access-token'),
  setProfile: vi.fn(),
  api: {
    listGroups: vi.fn(),
    saveMe: vi.fn(),
    uploadAvatar: vi.fn(),
  },
  savedProfile: {
    user_id: 'user-1',
    display_name: 'Alex',
    created_at: 'now',
    updated_at: 'now',
    avatar_url: null,
    non_essential_emails_enabled: false,
  },
}));

vi.mock('@ansavva/design-system', () => ({
  Button: ({ children, ...props }: Record<string, unknown> & { children?: unknown }) => (
    <button {...(props as Record<string, unknown>)}>{children as never}</button>
  ),
  Input: (props: Record<string, unknown>) => <input {...(props as Record<string, unknown>)} />,
  Textarea: (props: Record<string, unknown>) => <textarea {...(props as Record<string, unknown>)} />,
}));

vi.mock('../api/client', () => ({ api: mocks.api }));
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ accessToken: mocks.accessToken, email: 'alex@example.com' }),
}));
vi.mock('../context/ProfileContext', () => ({
  useProfile: () => ({ profile: null, loaded: true, setProfile: mocks.setProfile }),
}));

import DashboardPage from './DashboardPage';

describe('DashboardPage profile setup', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mocks.accessToken.mockResolvedValue('access-token');
    mocks.api.saveMe.mockResolvedValue(mocks.savedProfile);
    mocks.api.uploadAvatar.mockResolvedValue({ ...mocks.savedProfile, avatar_url: 'https://example.com/avatar.png' });
  });

  afterEach(() => cleanup());

  it('requires profile setup before loading app data and defaults optional email off', async () => {
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);

    expect(screen.getByText('One last detail')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Upload photo' })).toBeInTheDocument();
    const emailOptIn = screen.getByRole('checkbox') as HTMLInputElement;
    expect(emailOptIn).not.toBeChecked();
    expect(mocks.api.listGroups).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('Display name'), { target: { value: 'Alex' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    await waitFor(() => expect(mocks.api.saveMe).toHaveBeenCalledWith(
      'access-token',
      'Alex',
      false,
      expect.objectContaining({ version: expect.any(String), accepted_at: expect.any(String) }),
    ));
    expect(mocks.setProfile).toHaveBeenCalledWith(mocks.savedProfile);
  });

  it('saves an explicit email opt-in and uploads a selected profile picture', async () => {
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText('Display name'), { target: { value: 'Alex' } });
    fireEvent.click(screen.getByRole('checkbox'));
    const file = new File(['avatar'], 'avatar.png', { type: 'image/png' });
    fireEvent.change(screen.getByTestId('onboarding-avatar-input'), { target: { files: [file] } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Change photo' })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    await waitFor(() => expect(mocks.api.saveMe).toHaveBeenCalledWith(
      'access-token',
      'Alex',
      true,
      expect.any(Object),
    ));
    await waitFor(() => expect(mocks.api.uploadAvatar).toHaveBeenCalledWith(
      'access-token',
      expect.stringMatching(/^data:image\/png;base64,/),
    ));
    expect(mocks.setProfile).toHaveBeenCalledWith(expect.objectContaining({ avatar_url: 'https://example.com/avatar.png' }));
  });
});
