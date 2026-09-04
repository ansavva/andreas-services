// The create bar's state, held above the bar so the feed can drive it.
//
// **Why a context and not the bar's own `useState`.** The bar sits in `TopBar`
// and the things that fill it — Edit on a feed row, Use-in-prompt on a tile,
// Animate on an output, Use as → Reference in the opened run — sit in route
// elements nowhere near it. One provider above both is what lets a tile hand
// an image to a bar it cannot see, the same reason `SidebarContext` exists.
//
// **`useCreateBar()` is the cross-slice contract**: `loadRun`, `attach` and
// `setKind`, and nothing else. The bar itself reads `useCreateBarState()`, which
// is this file's own and free to change with the bar.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useMatch } from "react-router-dom";

import type { RunKind } from "../types";

/** What an attached image is FOR. The same four words a send's `role` takes. */
export type AttachRole = "reference" | "start" | "end" | "input";

/**
 * An image handed to the bar: the node it names, and enough to draw and to
 * say where it came from. `kind` mirrors a send's derived `source.kind`, so
 * a badge can say "run · #2" or "input 4" before the run exists.
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

/** What a feed row hands the bar to re-open a run in it. */
export interface CreateSeed {
  project: string;
  kind: RunKind;
  /** The Replicate `owner/name`, as the record carries it. */
  model?: string;
  prompt?: string;
  params?: Record<string, unknown>;
  attachments?: { ref: AttachRef; role: AttachRole }[];
}

export interface CreateBarApi {
  loadRun(seed: CreateSeed): void;
  attach(ref: AttachRef, role: AttachRole): void;
  setKind(kind: RunKind): void;
}

export interface Attachment {
  ref: AttachRef;
  role: AttachRole;
}

/** Where the last project the bar sent to survives a reload. */
export const CREATE_PROJECT_STORAGE_KEY = "studio.createBar.project";

/**
 * A role that holds ONE image. `start` and `end` are scalar fields on every
 * model that has them, and `input` — the image an edit starts from — is one
 * picture by meaning even where it lands on a list field. Attaching to any of
 * these replaces; only `reference` accumulates.
 */
export function holdsOne(role: AttachRole): boolean {
  return role !== "reference";
}

/** The kind a role belongs to. A frame is a video's; the rest fit either. */
function kindOfRole(role: AttachRole, current: RunKind): RunKind {
  return role === "start" || role === "end" ? "video" : current;
}

interface CreateBarState {
  kind: RunKind;
  /** The chosen model per kind — null means that kind's default. */
  model: Record<RunKind, string | null>;
  prompt: string;
  /**
   * Params a person set, keyed by model. Absent means the model's own
   * defaults, which the bar seeds from the registry snapshot on the way out —
   * so switching models never carries one model's `resolution` into another.
   */
  params: Record<string, Record<string, unknown>>;
  attachments: Record<RunKind, Attachment[]>;
  /** The project chosen IN the bar. The route's project beats it. */
  project: string | null;
  /** The highlighted role — the one the drawer supplies images for. */
  role: AttachRole | null;
  /** Keep the attached images after a send. */
  keep: boolean;
  /** Bumped when something loads the bar, so it can take focus. */
  focus: number;
}

interface CreateBarStateValue extends CreateBarState {
  /** The project a send goes to: the route's, else the bar's, else the last one used. */
  target: string | null;
  /** Whether `target` came off the route, which is when the picker is not drawn. */
  onProject: boolean;
  setPrompt(prompt: string): void;
  setModel(model: string | null): void;
  setParams(model: string, params: Record<string, unknown>): void;
  setProject(project: string | null): void;
  setRole(role: AttachRole | null): void;
  setKeep(keep: boolean): void;
  /** Take one attachment off the current kind. */
  detach(index: number): void;
  /** Take every attachment off the current kind. */
  clearAttachments(): void;
  /** After a send: the prompt goes, the images go unless kept. */
  sent(): void;
}

const ApiContext = createContext<CreateBarApi | null>(null);
const StateContext = createContext<CreateBarStateValue | null>(null);

function readProject(): string | null {
  try {
    return window.localStorage.getItem(CREATE_PROJECT_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeProject(project: string | null): void {
  try {
    if (project) window.localStorage.setItem(CREATE_PROJECT_STORAGE_KEY, project);
    else window.localStorage.removeItem(CREATE_PROJECT_STORAGE_KEY);
  } catch {
    /* private-mode Safari throws on the accessor; losing the memory is the lesser loss */
  }
}

const EMPTY: CreateBarState = {
  kind: "image",
  model: { image: null, video: null },
  prompt: "",
  params: {},
  attachments: { image: [], video: [] },
  project: null,
  role: null,
  keep: false,
  focus: 0,
};

export function CreateBarProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<CreateBarState>(() => ({
    ...EMPTY,
    project: readProject(),
  }));

  // The route's project, wherever under it the page is — a run opened at
  // `/p/<project>/r/<run>` is still that project's.
  const routeProject = useMatch("/p/:projectId/*")?.params.projectId ?? null;

  // The last project used is whichever one the person was last IN, so leaving
  // it for Home keeps the bar pointed where they were working.
  useEffect(() => {
    if (!routeProject) return;
    writeProject(routeProject);
    setState((current) =>
      current.project === routeProject ? current : { ...current, project: routeProject },
    );
  }, [routeProject]);

  const loadRun = useCallback((seed: CreateSeed) => {
    setState((current) => {
      const model = seed.model ?? current.model[seed.kind];
      const params =
        seed.model && seed.params ? { ...current.params, [seed.model]: seed.params } : current.params;
      return {
        ...current,
        kind: seed.kind,
        model: { ...current.model, [seed.kind]: model },
        prompt: seed.prompt ?? "",
        params,
        attachments: { ...current.attachments, [seed.kind]: seed.attachments ?? [] },
        project: seed.project,
        role: null,
        focus: current.focus + 1,
      };
    });
  }, []);

  const attach = useCallback((ref: AttachRef, role: AttachRole) => {
    setState((current) => {
      const kind = kindOfRole(role, current.kind);
      const held = current.attachments[kind];
      const next = holdsOne(role)
        ? [...held.filter((each) => each.role !== role), { ref, role }]
        : held.some((each) => each.role === role && each.ref.node === ref.node)
          ? held
          : [...held, { ref, role }];
      return {
        ...current,
        kind,
        attachments: { ...current.attachments, [kind]: next },
        focus: current.focus + 1,
      };
    });
  }, []);

  const setKind = useCallback((kind: RunKind) => {
    setState((current) => (current.kind === kind ? current : { ...current, kind, role: null }));
  }, []);

  const api = useMemo<CreateBarApi>(() => ({ loadRun, attach, setKind }), [loadRun, attach, setKind]);

  const setPrompt = useCallback(
    (prompt: string) => setState((current) => ({ ...current, prompt })),
    [],
  );
  const setModel = useCallback(
    (model: string | null) =>
      setState((current) => ({
        ...current,
        model: { ...current.model, [current.kind]: model },
      })),
    [],
  );
  const setParams = useCallback(
    (model: string, params: Record<string, unknown>) =>
      setState((current) => ({ ...current, params: { ...current.params, [model]: params } })),
    [],
  );
  const setProject = useCallback((project: string | null) => {
    writeProject(project);
    setState((current) => ({ ...current, project }));
  }, []);
  const setRole = useCallback(
    (role: AttachRole | null) => setState((current) => ({ ...current, role })),
    [],
  );
  const setKeep = useCallback((keep: boolean) => setState((current) => ({ ...current, keep })), []);
  const detach = useCallback(
    (index: number) =>
      setState((current) => ({
        ...current,
        attachments: {
          ...current.attachments,
          [current.kind]: current.attachments[current.kind].filter((_, at) => at !== index),
        },
      })),
    [],
  );
  const clearAttachments = useCallback(
    () =>
      setState((current) => ({
        ...current,
        attachments: { ...current.attachments, [current.kind]: [] },
      })),
    [],
  );
  const sent = useCallback(
    () =>
      setState((current) => ({
        ...current,
        prompt: "",
        role: null,
        attachments: current.keep
          ? current.attachments
          : { ...current.attachments, [current.kind]: [] },
      })),
    [],
  );

  const value = useMemo<CreateBarStateValue>(
    () => ({
      ...state,
      target: routeProject ?? state.project,
      onProject: routeProject !== null,
      setPrompt,
      setModel,
      setParams,
      setProject,
      setRole,
      setKeep,
      detach,
      clearAttachments,
      sent,
    }),
    [
      state,
      routeProject,
      setPrompt,
      setModel,
      setParams,
      setProject,
      setRole,
      setKeep,
      detach,
      clearAttachments,
      sent,
    ],
  );

  return (
    <ApiContext.Provider value={api}>
      <StateContext.Provider value={value}>{children}</StateContext.Provider>
    </ApiContext.Provider>
  );
}

/**
 * Drive the bar from anywhere under `AppLayout`.
 *
 * Throws outside the provider rather than returning a no-op, for the reason
 * `useShellSidebar` does: an Edit button that silently does nothing is a bug
 * whose call site looks correct.
 */
export function useCreateBar(): CreateBarApi {
  const ctx = useContext(ApiContext);
  if (!ctx) throw new Error("useCreateBar must be used inside <CreateBarProvider>");
  return ctx;
}

/** The bar's own reading of its state. Not part of the cross-slice contract. */
export function useCreateBarState(): CreateBarStateValue {
  const ctx = useContext(StateContext);
  if (!ctx) throw new Error("useCreateBarState must be used inside <CreateBarProvider>");
  return ctx;
}
