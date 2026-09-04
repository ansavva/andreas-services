// The create bar's API, as the rest of the app sees it.
//
// **A contract before an implementation.** The feed's Edit, Again, Upscale
// and Animate, the tile's "Use in prompt" and the opened run's "Use as" all
// hand something to the create bar — a whole run to start from, or one image
// with a role. The bar itself lands in slice 5; until then this provider
// stores the last call and renders its children, so every caller is wired to
// the real names and the real shapes now and nothing has to be re-plumbed
// when the bar arrives. Slice 5 replaces the BODY of this file and keeps the
// exports exactly as they are.
import {
  createContext,
  useContext,
  useMemo,
  useState,
  type JSX,
  type ReactNode,
} from "react";

import type { RunKind } from "../types";

/** What an attached image is FOR — the model's image slots, by role. */
export type AttachRole = "reference" | "start" | "end" | "input";

/**
 * One image handed to the bar: the node (what a send binds), the signed URL
 * (what the bar draws), and where it came from, so the bar can say
 * "run 2 · output 3" rather than a file name.
 */
export interface AttachRef {
  node: string;
  url: string;
  name: string;
  kind: "run" | "character" | "input-pool" | "object";
  run?: string;
  /** 1-based, matching what a runref's `#2` means. */
  output?: number;
  character?: string;
}

/** A whole run to start from — what Edit and Again load into the bar. */
export interface CreateSeed {
  project: string;
  kind: RunKind;
  model?: string;
  prompt?: string;
  params?: Record<string, unknown>;
  attachments?: { ref: AttachRef; role: AttachRole }[];
}

export interface CreateBarApi {
  /** Replace what the bar holds with this seed. */
  loadRun(seed: CreateSeed): void;
  /** Add one image to what the bar holds, in this role. */
  attach(ref: AttachRef, role: AttachRole): void;
  /** Switch the bar between image and video mode. */
  setKind(kind: RunKind): void;
}

/**
 * The last thing the bar was told — the stub's whole state, exposed for the
 * tests that assert a feed action reached the bar. Slice 5 owns the real
 * state and may drop this.
 */
export interface CreateBarLast {
  seed: CreateSeed | null;
  attachments: { ref: AttachRef; role: AttachRole }[];
  kind: RunKind;
}

const CreateBarContext = createContext<(CreateBarApi & { last: CreateBarLast }) | null>(null);

export function CreateBarProvider({ children }: { children: ReactNode }): JSX.Element {
  const [last, setLast] = useState<CreateBarLast>({
    seed: null,
    attachments: [],
    kind: "image",
  });

  const value = useMemo(
    () => ({
      last,
      loadRun(seed: CreateSeed) {
        setLast({ seed, attachments: seed.attachments ?? [], kind: seed.kind });
      },
      attach(ref: AttachRef, role: AttachRole) {
        setLast((current) => ({
          ...current,
          attachments: [...current.attachments, { ref, role }],
        }));
      },
      setKind(kind: RunKind) {
        setLast((current) => ({ ...current, kind }));
      },
    }),
    [last],
  );

  return <CreateBarContext.Provider value={value}>{children}</CreateBarContext.Provider>;
}

/**
 * The create bar, from anywhere under `AppLayout`.
 *
 * Throws outside the provider for the reason `useShellSidebar` does: a "Use
 * in prompt" that silently did nothing would be a bug whose call site looks
 * correct.
 */
export function useCreateBar(): CreateBarApi {
  const ctx = useContext(CreateBarContext);
  if (!ctx) throw new Error("useCreateBar must be used inside <CreateBarProvider>");
  return ctx;
}

/** The stub's last call, for tests. Slice 5 may remove this. */
export function useCreateBarLast(): CreateBarLast {
  const ctx = useContext(CreateBarContext);
  if (!ctx) throw new Error("useCreateBarLast must be used inside <CreateBarProvider>");
  return ctx.last;
}
