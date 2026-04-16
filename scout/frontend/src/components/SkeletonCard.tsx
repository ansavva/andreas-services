export function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 flex flex-col gap-3">
      <div className="h-4 bg-[var(--color-border)] rounded w-3/4" />
      <div className="h-3 bg-[var(--color-border)] rounded w-1/2" />
      <div className="h-3 bg-[var(--color-border)] rounded w-2/3" />
      <div className="h-12 bg-[var(--color-border)] rounded" />
    </div>
  );
}
