import { useRef, type PointerEvent as ReactPointerEvent } from "react";

/**
 * The grab strip at the top of the phone sheet, and the drag that dismisses
 * it.
 *
 * **The gesture lives on the strip, not the sheet.** A finger on the rows is
 * scrolling them, and the browser claims a vertical touch there for the
 * scroll (`pointercancel`) before this could read it; the strip is
 * `touch-action: none`, so a touch on it is ours from the first pixel. The
 * sheet follows the finger downward — never up — and lets go past 96px, or
 * past 24px with a flick; short of that it snaps back. Escape and the
 * backdrop still close it, so this is the phone's affordance rather than the
 * only one.
 */
export function SheetHandle({
  panel,
  onDismiss,
}: {
  panel: React.RefObject<HTMLDivElement | null>;
  onDismiss: () => void;
}) {
  const start = useRef<{ y: number; at: number } | null>(null);

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    start.current = { y: event.clientY, at: performance.now() };
    event.currentTarget.setPointerCapture(event.pointerId);
    if (panel.current) panel.current.style.transition = "none";
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const from = start.current;
    const sheet = panel.current;
    if (!from || !sheet) return;
    const dy = Math.max(0, event.clientY - from.y);
    sheet.style.transform = dy > 0 ? `translateY(${dy}px)` : "";
  };
  const onPointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    const from = start.current;
    const sheet = panel.current;
    start.current = null;
    if (!from || !sheet) return;
    const dy = event.clientY - from.y;
    const speed = dy / Math.max(1, performance.now() - from.at);
    sheet.style.transition = "transform 160ms ease-out";
    if (dy > 96 || (dy > 24 && speed > 0.6)) {
      sheet.style.transform = "translateY(100%)";
      window.setTimeout(onDismiss, 150);
    } else {
      sheet.style.transform = "";
    }
  };

  return (
    <div
      role="presentation"
      className="-mx-4 mb-2 flex h-8 cursor-grab touch-none items-center justify-center active:cursor-grabbing"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <span aria-hidden="true" className="block h-1 w-12 rounded-pill bg-fill-active" />
    </div>
  );
}
