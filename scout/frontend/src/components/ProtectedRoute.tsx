import { useAuth } from "@/context/AuthContext";
import { LoginForm } from "@/components/LoginForm";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { idToken, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--color-background)]">
        <div className="h-8 w-8 rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-primary)] animate-spin" />
      </div>
    );
  }

  if (!idToken) {
    return <LoginForm />;
  }

  return <>{children}</>;
}
