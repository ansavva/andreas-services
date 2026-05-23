import { useState } from "react";
import { Lock, LogIn } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

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

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-background)] px-4">
      <div className="w-full max-w-sm rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-card p-6">
        <div className="flex flex-col items-center gap-2 mb-6">
          <span className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-[var(--color-badge)] text-[var(--color-badge-text)]">
            <Lock size={20} />
          </span>
          <h1 className="text-lg font-semibold text-[var(--color-text-primary)]">Admin sign in</h1>
          <p className="text-xs text-[var(--color-text-muted)] text-center">
            Sign in with your Scout admin credentials.
          </p>
        </div>

        {!configured && (
          <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/40 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
            Cognito is not configured for this environment.
          </div>
        )}

        <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm text-[var(--color-text-secondary)]">
            Email
            <input
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-background)] text-[var(--color-text-primary)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
            />
          </label>

          <label className="flex flex-col gap-1 text-sm text-[var(--color-text-secondary)]">
            Password
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-background)] text-[var(--color-text-primary)] px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
            />
          </label>

          {error && (
            <div className="rounded-lg border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40 px-3 py-2 text-xs text-red-700 dark:text-red-400">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !configured}
            className="mt-1 inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50"
          >
            <LogIn size={16} />
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
