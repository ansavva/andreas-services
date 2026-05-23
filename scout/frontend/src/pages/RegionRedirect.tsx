import { Navigate } from "react-router-dom";
import { MapPin } from "lucide-react";
import { useRegions } from "@/hooks/useRegions";
import { Header } from "@/components/Header";

export function RegionRedirect() {
  const { regions, loading, error, refetch } = useRegions();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--color-background)]">
        <div className="h-8 w-8 rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-primary)] animate-spin" />
      </div>
    );
  }

  if (!error && regions.length > 0) {
    return <Navigate to={`/${regions[0].slug}`} replace />;
  }

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <Header onRefresh={refetch} loading={loading} />
      <main className="max-w-6xl mx-auto px-4 py-8">
        {error && (
          <div className="mb-6 rounded-lg border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-400">
            <strong>Could not load regions:</strong> {error}
          </div>
        )}
        <div className="flex flex-col items-center justify-center py-24 text-center gap-4">
          <MapPin size={48} className="text-[var(--color-text-muted)]" />
          <h2 className="text-lg font-medium text-[var(--color-text-secondary)]">No regions yet</h2>
          <p className="text-sm text-[var(--color-text-muted)] max-w-sm">
            Once events are published and assigned to a region, they will appear here.
          </p>
        </div>
      </main>
    </div>
  );
}
