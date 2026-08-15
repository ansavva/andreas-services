import { useCallback, useEffect, useRef, useState } from "react";

export type CopyStatus = "idle" | "copied" | "failed";

/** How long the button stays in its post-copy state before reverting. */
const FLASH_MS = 1600;

/**
 * Copy text, and remember for a moment whether it worked.
 *
 * The Clipboard API is the only path here, and it can reject — a tab that is not
 * the active document, a permission the browser declines — so failure is a state
 * the caller renders rather than a click that silently does nothing. Studio is
 * only ever served over HTTPS or localhost, both secure contexts, so a missing
 * `navigator.clipboard` means a browser we do not support rather than a
 * deployment we do; it lands in the same `failed` state.
 */
export function useCopyToClipboard(flashMs: number = FLASH_MS) {
  const [status, setStatus] = useState<CopyStatus>("idle");
  const timer = useRef<number | null>(null);

  // A tile can unmount while its flash is still running — navigating a folder
  // replaces the whole grid — so the timeout has to be cancellable.
  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );

  const copy = useCallback(
    async (text: string) => {
      let next: CopyStatus;
      try {
        await navigator.clipboard.writeText(text);
        next = "copied";
      } catch {
        next = "failed";
      }

      setStatus(next);
      if (timer.current !== null) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setStatus("idle"), flashMs);
    },
    [flashMs],
  );

  return { status, copy };
}

/**
 * One place for the three words a copy control can be showing, so a button and
 * its tooltip cannot describe the same state differently.
 */
export function copyLabel(status: CopyStatus, idle: string): string {
  if (status === "copied") return "Copied";
  if (status === "failed") return "Copy failed";
  return idle;
}
