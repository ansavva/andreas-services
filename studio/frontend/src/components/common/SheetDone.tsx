import { Button } from "@ansavva/design-system";

/**
 * The foot of a phone sheet: one full-width `Done`, stuck to the bottom edge.
 *
 * **Where a thumb is.** A bottom sheet capped at most of the screen puts its
 * grab strip near the top, which is the one place a thumb holding the phone
 * cannot reach — and the backdrop above it is the same sliver. The settings
 * sheet with a long schema and the picker with a grid of pictures are both
 * that tall, so each carries this at its foot: sticky on the sheet's own
 * background, so the rows scroll under it, and padded past the home
 * indicator on a phone that has one.
 *
 * `Done` rather than a ×: nothing on these sheets is a draft that could be
 * cancelled. A setting changed is changed, a picture attached is on the
 * bar, and the word says the sheet is only being put away.
 */
export function SheetDone({ onDone, label = "Done" }: { onDone: () => void; label?: string }) {
  return (
    <div
      className="sticky bottom-0 z-10 -mx-6 -mb-6 mt-auto shrink-0 border-t border-line bg-card px-6 pt-3
                 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
    >
      <Button size="md" intent="secondary" className="w-full" onClick={onDone}>
        {label}
      </Button>
    </div>
  );
}
