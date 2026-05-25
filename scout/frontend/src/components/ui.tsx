import { X } from "lucide-react";

export function Spinner() {
  return (
    <div className="h-6 w-6 rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-primary)] animate-spin" />
  );
}

export function Chip({
  label,
  active = false,
  onClick,
}: {
  label: string;
  active?: boolean;
  onClick?: () => void;
}) {
  const base =
    "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium transition-colors";
  const tone = active
    ? "bg-[var(--color-primary)] text-white"
    : "bg-[var(--color-badge)] text-[var(--color-badge-text)] hover:opacity-80";
  return onClick ? (
    <button type="button" onClick={onClick} className={`${base} ${tone}`}>
      {label}
    </button>
  ) : (
    <span className={`${base} ${tone}`}>{label}</span>
  );
}

const BADGE_TONES: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-400",
  approved: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400",
  rejected: "bg-red-100 text-red-800 dark:bg-red-950/50 dark:text-red-400",
  published: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400",
  unpublished: "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  error: "bg-red-100 text-red-800 dark:bg-red-950/50 dark:text-red-400",
  success: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400",
  in_progress: "bg-sky-100 text-sky-800 dark:bg-sky-950/50 dark:text-sky-400",
};

export function Badge({ value }: { value: string }) {
  const tone =
    BADGE_TONES[value] ??
    "bg-[var(--color-badge)] text-[var(--color-badge-text)]";
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${tone}`}>
      {value}
    </span>
  );
}

export function Button({
  children,
  onClick,
  variant = "default",
  type = "button",
  disabled = false,
  title,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "default" | "primary" | "danger" | "ghost";
  type?: "button" | "submit";
  disabled?: boolean;
  title?: string;
}) {
  const tones: Record<string, string> = {
    primary:
      "bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white",
    danger: "bg-red-600 hover:bg-red-700 text-white",
    default:
      "border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]",
    ghost: "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${tones[variant]}`}
    >
      {children}
    </button>
  );
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg max-h-[85vh] overflow-y-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-[var(--color-text-primary)]">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]"
          >
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-400">
      {message}
    </div>
  );
}
