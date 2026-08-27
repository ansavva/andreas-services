import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

function Spinner() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-background)]">
      <div className="h-8 w-8 rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-primary)] animate-spin" />
    </div>
  );
}

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { idToken, loading, configured, login } = useAuth();
  const location = useLocation();

  // No in-app form any more: an unauthenticated visit bounces to the hosted
  // sign-in page and comes back to this path via /auth/callback.
  useEffect(() => {
    if (loading || idToken || !configured) return;
    void login(`${location.pathname}${location.search}`);
  }, [loading, idToken, configured, login, location.pathname, location.search]);

  if (!configured) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-background)] px-5">
        <div className="w-full max-w-sm border border-[var(--color-rule)] bg-[var(--color-surface)] p-8">
          <p className="eyebrow text-[var(--color-text-muted)]">Scout</p>
          <h1 className="mt-3 font-serif text-2xl text-[var(--color-text-primary)]">
            Sign-in unavailable
          </h1>
          <p className="mt-2 text-sm text-[var(--color-text-muted)]">
            This build has no Cognito configuration, so admin sign-in cannot start.
          </p>
        </div>
      </div>
    );
  }

  // Signed out, redirect in flight — never flash the admin UI behind it.
  if (loading || !idToken) return <Spinner />;

  return <>{children}</>;
}
