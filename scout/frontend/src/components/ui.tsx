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
    "inline-flex items-center rounded-none border px-2.5 py-1 text-[11px] uppercase tracking-[0.12em] transition-colors";
  const tone = active
    ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-white"
    : "border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-text-primary)] hover:text-[var(--color-text-primary)]";
  return onClick ? (
    <button type="button" onClick={onClick} className={`${base} ${tone}`}>
      {label}
    </button>
  ) : (
    <span className={`${base} ${tone}`}>{label}</span>
  );
}

// Affirmative / live states read as a solid black fill; everything else is a
// hairline outline. Monochrome by design — the label word carries the meaning.
const FILLED_BADGES = new Set([
  "approved",
  "published",
  "success",
  "active",
  "in_progress",
]);

export function Badge({ value }: { value: string }) {
  const filled = FILLED_BADGES.has(value);
  const tone = filled
    ? "bg-[var(--color-primary)] text-white"
    : "border border-[var(--color-border)] text-[var(--color-text-secondary)]";
  return (
    <span
      className={`inline-flex rounded-none px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.1em] ${tone}`}
    >
      {value.replace(/_/g, " ")}
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
      "border border-[var(--color-primary)] bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)]",
    default:
      "border border-[var(--color-border)] text-[var(--color-text-primary)] hover:border-[var(--color-text-primary)]",
    danger:
      "border border-[var(--color-text-primary)] text-[var(--color-text-primary)] hover:bg-[var(--color-text-primary)] hover:text-white",
    ghost:
      "text-[var(--color-text-secondary)] underline-offset-4 hover:text-[var(--color-text-primary)] hover:underline",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`inline-flex min-h-[40px] items-center justify-center gap-1.5 rounded-none px-4 py-2 text-[11px] font-medium uppercase tracking-[0.12em] transition-colors disabled:opacity-40 ${tones[variant]}`}
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
      className="fixed inset-0 z-30 flex items-end justify-center bg-black/30 sm:items-center sm:px-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[100dvh] w-full flex-col overflow-hidden border border-[var(--color-rule)] bg-[var(--color-surface)] sm:max-h-[85vh] sm:max-w-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-5 py-4">
          <h2 className="font-serif text-xl leading-none text-[var(--color-text-primary)]">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="-mr-1 rounded-none p-2 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
          >
            <X size={18} />
          </button>
        </div>
        <div className="overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="border-l-2 border-[var(--color-rule)] bg-[var(--color-surface-hover)] px-4 py-3 text-sm text-[var(--color-text-primary)]">
      {message}
    </div>
  );
}
