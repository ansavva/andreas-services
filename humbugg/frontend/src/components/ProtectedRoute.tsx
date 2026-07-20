import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';

import { useAuth } from '../context/AuthContext';
import { useProfile } from '../context/ProfileContext';

export default function ProtectedRoute({ children, allowMissingProfile = false }: { children: ReactNode; allowMissingProfile?: boolean }) {
  const auth = useAuth();
  const { loaded: profileLoaded, profile } = useProfile();
  const location = useLocation();

  if (auth.loading) return <div className="loading-panel min-h-screen">Checking your session…</div>;
  if (!auth.authenticated) {
    if (typeof window !== 'undefined') {
      sessionStorage.setItem('humbugg:returnTo', `${location.pathname}${location.search}${location.hash}`);
    }
    return <Navigate to="/login" replace />;
  }
  if (!profileLoaded) return <div className="loading-panel min-h-screen">Loading your profile…</div>;
  if (!allowMissingProfile && !profile) return <Navigate to="/app" replace />;
  return children;
}
