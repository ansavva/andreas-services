import { useCallback, useEffect, useState } from "react";

/**
 * One panel open at a time, in the slot the control that opened it sits in.
 *
 * **The pattern this holds is "the form takes over where you pressed".** Three
 * surfaces grew three different answers to the same interaction — the plan
 * editor replaced its trigger in place, the run composer was permanently open
 * with no trigger at all, and promote hid its trigger and drew its form below
 * the whole outputs grid, which is the one that reads as disconnected: with
 * several outputs you press the third tile and the form opens past all of them.
 * Adjacency is what makes a panel legible as belonging to the thing pressed;
 * nothing drawn between them substitutes for it.
 *
 * Keyed rather than boolean, because two of the three are per-item — an output
 * has a promote panel each — and "which one" and "one at a time" are the same
 * fact. A boolean per item cannot express the second.
 *
 * **Escape is guarded, and that is not a detail.** A panel holding typed words
 * that vanishes on a stray Escape loses them with no undo, so `canClose` is
 * asked first and a dirty form simply declines. The plan editor does not use
 * this at all: what it holds is a whole document, and its Cancel is a decision
 * rather than a dismissal.
 */
export function useDisclosure<T extends string = string>(
  canClose: () => boolean = () => true,
) {
  const [open, setOpen] = useState<T | null>(null);

  const close = useCallback(() => setOpen(null), []);

  /** Press the same control again to put the panel away. */
  const toggle = useCallback(
    (id: T) => setOpen((current) => (current === id ? null : id)),
    [],
  );

  const isOpen = useCallback((id: T) => open === id, [open]);

  useEffect(() => {
    if (open === null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (!canClose()) return;
      setOpen(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // `canClose` is read at the moment Escape lands rather than depended on:
    // it closes over the form's current values, so listing it here would tear
    // the listener down and rebuild it on every keystroke.
  }, [open, canClose]);

  return { open, isOpen, toggle, close };
}
