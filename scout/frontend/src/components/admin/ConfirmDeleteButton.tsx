import { useEffect, useRef, useState } from "react";
import { Check, Loader2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui";

/**
 * Two-step delete control: the first click arms the button (it shows a confirm
 * affordance), the second click within a few seconds commits. It auto-disarms
 * so a stray first click is harmless — no separate confirmation dialog needed.
 *
 * `compact` renders a small icon-only button for tight spots (e.g. label chips);
 * the default renders a danger Button matching the other row actions. `onArm`
 * fires when the button is armed so a caller can lazily fetch a cascade preview
 * to show in `confirmLabel`.
 */
export function ConfirmDeleteButton({
  onConfirm,
  onArm,
  confirmLabel = "Confirm?",
  busy = false,
  disabled = false,
  title = "Delete",
  compact = false,
}: {
  onConfirm: () => void;
  onArm?: () => void;
  confirmLabel?: string;
  busy?: boolean;
  disabled?: boolean;
  title?: string;
  compact?: boolean;
}) {
  const [armed, setArmed] = useState(false);
  const timer = useRef<number | null>(null);

  const clear = () => {
    if (timer.current) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  };
  useEffect(() => clear, []);

  const click = () => {
    if (busy) return;
    if (!armed) {
      setArmed(true);
      onArm?.();
      timer.current = window.setTimeout(() => setArmed(false), 4000);
      return;
    }
    clear();
    setArmed(false);
    onConfirm();
  };

  const tip = armed ? "Click again to confirm" : title;

  if (compact) {
    return (
      <button
        type="button"
        disabled={disabled}
        onClick={click}
        title={tip}
        className={`rounded-none p-1 transition-colors ${
          armed
            ? "text-[var(--color-primary)]"
            : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
        }`}
      >
        {busy ? (
          <Loader2 size={13} className="animate-spin" />
        ) : armed ? (
          <Check size={13} />
        ) : (
          <Trash2 size={13} />
        )}
      </button>
    );
  }

  return (
    <Button variant="danger" disabled={disabled} onClick={click} title={tip}>
      {busy ? (
        <Loader2 size={14} className="animate-spin" />
      ) : armed ? (
        <>
          <Check size={14} />
          {confirmLabel}
        </>
      ) : (
        <Trash2 size={14} />
      )}
    </Button>
  );
}
