// The create bar's state, held above the bar so the feed can drive it.
//
// **Why a context and not the bar's own `useState`.** The bar sits in `TopBar`
// and the things that fill it — Edit on a feed row, Use-in-prompt on a tile,
// Start frame on an output, Use as → Reference in the opened run — sit in route
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
  /**
   * The thumbnail's URL, and the name beside it — both absent when the node the
   * ref names is gone.
   *
   * **The node is what a send is made of; these two are only how it is drawn.**
   * A run loaded into the bar from a row whose send was deleted keeps that
   * attachment rather than quietly dropping it: an image vanishing from a
   * re-run without a word changes what gets sent, and the chip that says
   * `Unavailable` is the thing that lets a person notice and remove it. See
   * `RunAsset`, which is where the absence comes from.
   */
  url?: string | null;
  name?: string;
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
 * Where "I collapsed the sheet" survives a reload.
 *
 * **Remembered, because the point of collapsing it is to browse without it.**
 * A collapse that undid itself on the next navigation would be a control that
 * does nothing you can use — and the sheet is drawn on every screen, so "every
 * screen" is exactly the scope of the decision.
 */
export const CREATE_COLLAPSED_STORAGE_KEY = "studio.createBar.collapsed";

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
  /** Bumped when something loads the bar, so it can take focus. */
  focus: number;
  /**
   * Whether something has called the sheet up since the run or file on
   * screen was opened. On the opened run — and the open file, which is the
   * same viewer — the sheet is not drawn until Edit, Rerun, Use as reference
   * or a tile attaches something — it would cover the filmstrip and the
   * transport with a prompt about some other run. Reset every time a
   * different one opens. Read as `shown`.
   */
  summoned: boolean;
  /**
   * Collapsed by hand, on every screen, until it is pulled back up.
   *
   * **Separate from `summoned`, which is about one screen.** The opened run
   * keeps the sheet away because a prompt about some other run would cover the
   * filmstrip; this is a person saying they want the feed to themselves. Both
   * have to be false for the sheet to be drawn, and anything that fills the
   * sheet clears this one — attaching a picture to a sheet nobody can see is
   * the one outcome this must not have.
   */
  collapsed: boolean;
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
  /** Take one attachment off the current kind. */
  detach(index: number): void;
  /** The start frame becomes the end frame and vice versa. A no-op unless both are held. */
  swapFrames(): void;
  /** Whether the sheet is drawn at all — false on the opened run until something calls it up. */
  shown: boolean;
  /** Collapse the sheet to its handle. */
  collapse(): void;
  /** Pull it back up, with the caret in the prompt. */
  expand(): void;
  /** After a send: the prompt goes, the images go unless kept. */
  sent(): void;
}

const ApiContext = createContext<CreateBarApi | null>(null);
const StateContext = createContext<CreateBarStateValue | null>(null);

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(CREATE_COLLAPSED_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeCollapsed(collapsed: boolean): void {
  try {
    if (collapsed) window.localStorage.setItem(CREATE_COLLAPSED_STORAGE_KEY, "1");
    else window.localStorage.removeItem(CREATE_COLLAPSED_STORAGE_KEY);
  } catch {
    /* private-mode Safari throws on the accessor; losing the memory is the lesser loss */
  }
}

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
  focus: 0,
  summoned: false,
  collapsed: false,
};

export function CreateBarProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<CreateBarState>(() => ({
    ...EMPTY,
    project: readProject(),
    collapsed: readCollapsed(),
  }));

  // The route's project, wherever under it the page is — a run opened at
  // `/p/<project>/r/<run>` is still that project's.
  const routeProject = useMatch("/p/:projectId/*")?.params.projectId ?? null;
  // The opened run and the open file — the two screens the sheet stays out
  // of until it is called up: both are `ViewerFrame`, sized to the window, and
  // a sheet drawn over either covers the strip and the transport with nothing
  // able to scroll them back. Keyed on the id so a different one opening puts
  // it away again.
  const openedRun = useMatch("/p/:projectId/r/:runId")?.params.runId ?? null;
  const openedFile = useMatch("/o/:nodeId")?.params.nodeId ?? null;
  const opened = openedRun ?? openedFile;
  useEffect(() => {
    setState((current) => (current.summoned ? { ...current, summoned: false } : current));
  }, [opened]);

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
        summoned: true,
        collapsed: false,
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
      // No focus bump: a tile pressed in the drawer must not pull the caret
      // away from the drawer it was pressed in.
      return {
        ...current,
        kind,
        attachments: { ...current.attachments, [kind]: next },
        summoned: true,
        collapsed: false,
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
  /**
   * After a send: the prompt goes, and so do the images.
   *
   * **There is no "keep these" any more.** A padlock beside the tiles held them
   * for the next send and a bin next to it emptied them, which is two controls
   * and a piece of state for something the tiles already do one at a time —
   * every tile carries its own ×, and attaching again is a press. Dropped on
   * request; what is left is the one behaviour a send should have.
   */
  const sent = useCallback(
    () =>
      setState((current) => ({
        ...current,
        prompt: "",
        role: null,
        attachments: { ...current.attachments, [current.kind]: [] },
      })),
    [],
  );

  const swapFrames = useCallback(
    () =>
      setState((current) => {
        const held = current.attachments.video;
        if (!held.some((each) => each.role === "start") || !held.some((each) => each.role === "end"))
          return current;
        const swapped = held.map((each) =>
          each.role === "start"
            ? { ...each, role: "end" as const }
            : each.role === "end"
              ? { ...each, role: "start" as const }
              : each,
        );
        return { ...current, attachments: { ...current.attachments, video: swapped } };
      }),
    [],
  );

  const collapse = useCallback(() => {
    writeCollapsed(true);
    setState((current) => ({ ...current, summoned: false, collapsed: true, role: null }));
  }, []);

  /**
   * Pull it back up, and put the caret in the prompt.
   *
   * `focus` is the bump the bar watches — the same one `loadRun` uses — so
   * opening the sheet lands you in the box you opened it to type in.
   */
  const expand = useCallback(() => {
    writeCollapsed(false);
    setState((current) => ({
      ...current,
      collapsed: false,
      summoned: true,
      focus: current.focus + 1,
    }));
  }, []);

  const value = useMemo<CreateBarStateValue>(
    () => ({
      ...state,
      target: routeProject ?? state.project,
      onProject: routeProject !== null,
      // Both have to be clear: `collapsed` is a person's decision about every
      // screen, `summoned` is this screen's own rule about the opened run.
      shown: !state.collapsed && (opened === null || state.summoned),
      collapse,
      expand,
      setPrompt,
      setModel,
      setParams,
      setProject,
      setRole,
      detach,
      swapFrames,
      sent,
    }),
    [
      state,
      routeProject,
      opened,
      collapse,
      expand,
      setPrompt,
      setModel,
      setParams,
      setProject,
      setRole,
      detach,
      swapFrames,
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
