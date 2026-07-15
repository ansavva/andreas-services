import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';

import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const location = useLocation();

  if (auth.loading) return <div className="loading-panel min-h-screen">Checking your session…</div>;
  if (!auth.authenticated) {
    if (typeof window !== 'undefined') {
      sessionStorage.setItem('humbugg:returnTo', `${location.pathname}${location.search}${location.hash}`);
    }
    return <Navigate to="/login" replace />;
  }
  return children;
}
