import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { handleCallback } from "@/auth/oauth";

/**
 * Landing point for the hosted sign-in redirect. Exchanges the authorization
 * code for tokens, then continues to wherever the user was headed.
 */
export function AuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { syncFromStore, login } = useAuth();
  const [error, setError] = useState<string | null>(null);

  // An authorization code is single-use; StrictMode's double effect would
  // spend it twice and fail the second exchange.
  const exchanged = useRef(false);

  useEffect(() => {
    if (exchanged.current) return;
    exchanged.current = true;

    handleCallback(searchParams)
      .then((returnTo) => {
        syncFromStore();
        navigate(returnTo, { replace: true });
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Sign-in failed.");
      });
  }, [searchParams, syncFromStore, navigate]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-background)] px-5">
        <div className="w-full max-w-sm border border-[var(--color-rule)] bg-[var(--color-surface)] p-8">
          <p className="eyebrow text-[var(--color-text-muted)]">Scout</p>
          <h1 className="mt-3 font-serif text-2xl text-[var(--color-text-primary)]">
            Sign-in failed
          </h1>
          <p className="mt-2 text-sm text-[var(--color-text-muted)]">{error}</p>
          <button
            type="button"
            onClick={() => void login("/admin")}
            className="mt-6 w-full border border-[var(--color-rule)] px-4 py-2 text-sm text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-background)]">
      <div className="h-8 w-8 rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-primary)] animate-spin" />
    </div>
  );
}
