// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';

const mocks = vi.hoisted(() => ({
  auth: { authenticated: true, loading: false },
  profile: { loaded: true, profile: null as { user_id: string } | null },
}));

vi.mock('../context/AuthContext', () => ({ useAuth: () => mocks.auth }));
vi.mock('../context/ProfileContext', () => ({ useProfile: () => mocks.profile }));

import ProtectedRoute from './ProtectedRoute';

function renderProtected(allowMissingProfile = false) {
  render(
    <MemoryRouter initialEntries={['/app/settings']}>
      <Routes>
        <Route path="/app" element={<div>App home</div>} />
        <Route
          path="/app/settings"
          element={<ProtectedRoute allowMissingProfile={allowMissingProfile}><div>Settings</div></ProtectedRoute>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProtectedRoute profile requirement', () => {
  beforeEach(() => {
    mocks.auth.authenticated = true;
    mocks.auth.loading = false;
    mocks.profile.loaded = true;
    mocks.profile.profile = null;
  });

  afterEach(() => cleanup());

  it('redirects an authenticated user without a profile to the app home', () => {
    renderProtected();
    expect(screen.getByText('App home')).toBeInTheDocument();
    expect(screen.queryByText('Settings')).not.toBeInTheDocument();
  });

  it('allows the app home to render profile setup without a profile', () => {
    renderProtected(true);
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

  it('allows other app pages once the profile exists', () => {
    mocks.profile.profile = { user_id: 'user-1' };
    renderProtected();
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

  it('waits for the profile lookup before rendering a protected app page', () => {
    mocks.profile.loaded = false;
    renderProtected();
    expect(screen.getByText('Loading your profile…')).toBeInTheDocument();
    expect(screen.queryByText('Settings')).not.toBeInTheDocument();
  });
});
