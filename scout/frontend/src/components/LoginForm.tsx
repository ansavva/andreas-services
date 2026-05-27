import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { ErrorBanner } from "@/components/ui";

export function LoginForm() {
  const { login, configured } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  const field =
    "w-full rounded-none border-b border-[var(--color-rule)] bg-transparent py-2 text-sm text-[var(--color-text-primary)] focus:outline-none";

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-background)] px-5">
      <div className="w-full max-w-sm border border-[var(--color-rule)] bg-[var(--color-surface)] p-8">
        <p className="eyebrow text-[var(--color-text-muted)]">Scout</p>
        <h1 className="mt-3 font-serif text-2xl text-[var(--color-text-primary)]">
          Admin sign in
        </h1>
        <p className="mt-2 text-sm text-[var(--color-text-muted)]">
          Sign in with your Scout admin credentials.
        </p>

        {!configured && (
          <div className="mt-6 border-l-2 border-[var(--color-rule)] bg-[var(--color-surface-hover)] px-4 py-3 text-xs text-[var(--color-text-secondary)]">
            Cognito is not configured for this environment.
          </div>
        )}

        <form onSubmit={(e) => void handleSubmit(e)} className="mt-6 flex flex-col gap-5">
          <label className="flex flex-col gap-1.5">
            <span className="eyebrow text-[var(--color-text-muted)]">Email</span>
            <input
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={field}
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="eyebrow text-[var(--color-text-muted)]">Password</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={field}
            />
          </label>

          {error && <ErrorBanner message={error} />}

          <button
            type="submit"
            disabled={submitting || !configured}
            className="mt-1 min-h-[44px] w-full rounded-none border border-[var(--color-primary)] bg-[var(--color-primary)] px-4 py-3 text-[11px] font-medium uppercase tracking-[0.14em] text-white transition-colors hover:bg-[var(--color-primary-hover)] disabled:opacity-40"
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
