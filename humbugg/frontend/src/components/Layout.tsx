import { Button } from '@ansavva/design-system';
import { Link, useNavigate } from 'react-router';
import type { HTMLAttributes, ReactNode } from 'react';

import { useAuth } from '../context/AuthContext';

export function Brand() {
  return (
    <Link to="/" className="group flex items-center" aria-label="Humbugg home">
      <span className="brand-wordmark">Humbugg</span>
    </Link>
  );
}

export function Shell({ children, compact = false }: { children: ReactNode; compact?: boolean }) {
  const auth = useAuth();
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-bg text-ink">
      <header className="border-b border-line/80 bg-bg/95 backdrop-blur">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-5 lg:px-8">
          <Brand />
          <nav className="flex items-center gap-2" aria-label="Primary navigation">
            {auth.authenticated ? (
              <>
                <Button className="font-body text-sm font-medium leading-none" intent="ghost" onClick={() => navigate('/app')}>My groups</Button>
                <Button className="font-body text-sm font-medium leading-none" intent="ghost" onClick={() => void auth.logout().then(() => navigate('/'))}>Sign out</Button>
              </>
            ) : (
              <>
                <Link className="nav-link hidden sm:inline-flex" to="/login">Sign in</Link>
                <Button onClick={() => navigate('/signup')}>Start a group</Button>
              </>
            )}
          </nav>
        </div>
      </header>
      <main className={compact ? '' : 'mx-auto max-w-7xl px-5 py-10 lg:px-8'}>{children}</main>
    </div>
  );
}

export function StatusMessage({ message, tone = 'error' }: { message?: string | null; tone?: 'error' | 'success' }) {
  if (!message) return null;
  return <div role="status" className={`status-message ${tone === 'success' ? 'status-success' : 'status-error'}`}>{message}</div>;
}

export function Card({ children, className = '', ...props }: HTMLAttributes<HTMLElement> & { children: ReactNode }) {
  return <section className={`rounded-2xl border border-line bg-card p-6 shadow-sm ${className}`} {...props}>{children}</section>;
}
