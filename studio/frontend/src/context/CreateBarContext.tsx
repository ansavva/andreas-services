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
import { useQuery } from "@tanstack/react-query";

import { getMovie, getScene } from "../apis/studio";

import type { RunKind } from "../types";

/** What an attachment is FOR. The same five words a send's `role` takes. */
export type AttachRole = "reference" | "start" | "end" | "input" | "clip";

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
  kind: "run" | "character" | "location" | "input-pool" | "object";
  run?: string;
  /** 1-based, matching what a runref's `#2` means. */
  output?: number;
  character?: string;
  /** The location whose tree the picture sits in — the run records it as shot there. */
  location?: string;
  /**
   * Set while the thing this ref names is still being MADE — a clip's first
   * frame the worker has not handed back yet. The sentence is what the tile
   * says. `node` is then a placeholder that exists nowhere; `sendsOf` skips
   * it and the bar will not send while one is held, and `replace` swaps it
   * for the real ref when the work lands (or `drop` takes it off when it
   * fails). `url`, when set, is the source it is being made from, so the
   * tile has a picture to wait over.
   */
  pending?: string;
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
  /** Swap the attachment naming `node` for `ref`, in the role it held. A no-op if it is gone. */
  replace(node: string, ref: AttachRef): void;
  /** Take every attachment naming `node` off, whichever kind holds it. */
  drop(node: string): void;
  setKind(kind: RunKind): void;
}

export interface Attachment {
  ref: AttachRef;
  role: AttachRole;
}

/** Where the last project the bar sent to survives a reload. */
export const CREATE_PROJECT_STORAGE_KEY = "studio.createBar.project";

/**
 * A role that holds ONE object. `start`, `end` and `clip` are scalar fields on
 * every model that has them, and `input` — the image an edit starts from — is
 * one picture by meaning even where it lands on a list field. Attaching to any
 * of these replaces; only `reference` accumulates.
 */
export function holdsOne(role: AttachRole): boolean {
  return role !== "reference";
}

/** The kind a role belongs to. A frame or a clip is a video's; the rest fit either. */
function kindOfRole(role: AttachRole, current: RunKind): RunKind {
  return role === "start" || role === "end" || role === "clip" ? "video" : current;
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
   * Bumped when something loads the sheet with words to read — `loadRun`,
   * `summon` — so the shell can scroll it into view. **Not by `attach`**: a
   * picture handed up from a feed row half a page down lands in the dock
   * the sheet leaves in the window's corner once it has scrolled away
   * (`AttachDock`), which is where the next one is dragged to, and pulling
   * the page to the top on every drop would take the dock away from under
   * the drag. Not by `replace` or `drop` either, which are the worker
   * finishing, not a person acting.
   */
  raised: number;
  /**
   * Whether something has called the sheet up since the run or file on
   * screen was opened. On the opened run — and the open file, which is the
   * same viewer — the sheet is not drawn until Edit, Rerun, Use as reference
   * or a tile attaches something — it would cover the filmstrip and the
   * transport with a prompt about some other run. Reset every time a
   * different one opens. Read as `shown`.
   *
   * **This is the only way the sheet is ever not drawn.** It used to collapse
   * to a handle on every screen, remembered across reloads; now it sits in
   * the page's flow at the top, scrolls away like the rest of the page, and
   * needs no folding. The opened run is the one screen where it is drawn
   * OVER something, so it is the one screen with a way to put it away again.
   */
  summoned: boolean;
}

interface CreateBarStateValue extends CreateBarState {
  /** The project a send goes to: the route's, else the bar's, else the last one used. */
  target: string | null;
  /** Whether `target` came off the route, which is when the picker is not drawn. */
  onProject: boolean;
  /**
   * The scene a send is filed under: the route's, on `/s/<scene>`, else
   * none. A run made from a scene page belongs to that scene from the draft —
   * the page lists its runs off the field, so a run filed later is one nobody
   * saw.
   */
  scene: string | null;
  setPrompt(prompt: string): void;
  setModel(model: string | null): void;
  setParams(model: string, params: Record<string, unknown>): void;
  setProject(project: string | null): void;
  setRole(role: AttachRole | null): void;
  /** Take one attachment off the current kind. */
  detach(index: number): void;
  /** The start frame becomes the end frame and vice versa. A no-op unless both are held. */
  swapFrames(): void;
  /**
   * Move one attachment of the current kind so it sits at another's index.
   * Attachment order is send order, so this is what "Image 2 before Image 1"
   * means. Both indices are into the current kind's list.
   */
  move(from: number, to: number): void;
  /** Whether the sheet is drawn at all — false on the opened run until something calls it up. */
  shown: boolean;
  /** Whether the sheet, when drawn, is over the opened run's viewer rather than on a page. */
  overViewer: boolean;
  /** Call the sheet up on the opened run, with the caret in the prompt. */
  summon(): void;
  /** Put it away again on the opened run. A no-op anywhere else, where it is always drawn. */
  dismiss(): void;
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
  model: { image: null, video: null, training: null },
  prompt: "",
  params: {},
  attachments: { image: [], video: [], training: [] },
  project: null,
  role: null,
  focus: 0,
  raised: 0,
  summoned: false,
};

export function CreateBarProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<CreateBarState>(() => ({
    ...EMPTY,
    project: readProject(),
  }));

  // The route's project, wherever under it the page is — a run opened at
  // `/p/<project>/r/<run>` is still that project's.
  const routeProject = useMatch("/p/:projectId/*")?.params.projectId ?? null;
  // A scene page names no project in its URL, so the scene is read to learn
  // which project a send goes to. Cached under the page's own key, so the
  // page and the bar share one read.
  const routeScene = useMatch("/s/:sceneId")?.params.sceneId ?? null;
  const scene = useQuery({
    queryKey: ["scene", routeScene],
    queryFn: () => getScene(routeScene ?? ""),
    enabled: routeScene !== null,
  });
  const sceneProject = scene.data?.project ?? null;
  // A movie page is the same shape: no project in its URL, the movie's
  // record says which. Without this the bar drew the picker on a movie and
  // hid it on the movie's own scenes.
  const routeMovie = useMatch("/m/:movieId")?.params.movieId ?? null;
  const movie = useQuery({
    queryKey: ["movie", routeMovie],
    queryFn: () => getMovie(routeMovie ?? ""),
    enabled: routeMovie !== null,
  });
  const movieProject = movie.data?.project ?? null;
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
    const here = routeProject ?? sceneProject ?? movieProject;
    if (!here) return;
    writeProject(here);
    setState((current) =>
      current.project === here ? current : { ...current, project: here },
    );
  }, [routeProject, sceneProject, movieProject]);

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
        raised: current.raised + 1,
        summoned: true,
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
      };
    });
  }, []);

  // Across BOTH kinds, because the caller holds a node, not a kind: a frame
  // attached as a reference while the bar was on Image, then switched to
  // Video by the person, is still the same placeholder to swap or drop.
  const replace = useCallback((node: string, ref: AttachRef) => {
    setState((current) => ({
      ...current,
      attachments: {
        image: current.attachments.image.map((each) => (each.ref.node === node ? { ...each, ref } : each)),
        video: current.attachments.video.map((each) => (each.ref.node === node ? { ...each, ref } : each)),
        training: current.attachments.training,
      },
    }));
  }, []);

  const drop = useCallback((node: string) => {
    setState((current) => ({
      ...current,
      attachments: {
        image: current.attachments.image.filter((each) => each.ref.node !== node),
        video: current.attachments.video.filter((each) => each.ref.node !== node),
        training: current.attachments.training,
      },
    }));
  }, []);

  const setKind = useCallback((kind: RunKind) => {
    setState((current) => (current.kind === kind ? current : { ...current, kind, role: null }));
  }, []);

  const api = useMemo<CreateBarApi>(
    () => ({ loadRun, attach, replace, drop, setKind }),
    [loadRun, attach, replace, drop, setKind],
  );

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

  const move = useCallback(
    (from: number, to: number) =>
      setState((current) => {
        const held = current.attachments[current.kind];
        if (from === to || !(from in held) || !(to in held)) return current;
        const moved = [...held];
        const [one] = moved.splice(from, 1);
        moved.splice(to, 0, one!);
        return { ...current, attachments: { ...current.attachments, [current.kind]: moved } };
      }),
    [],
  );

  const dismiss = useCallback(() => {
    setState((current) => (current.summoned ? { ...current, summoned: false, role: null } : current));
  }, []);

  /**
   * Call it up, and put the caret in the prompt.
   *
   * `focus` is the bump the bar watches — the same one `loadRun` uses — so
   * opening the sheet lands you in the box you opened it to type in.
   */
  const summon = useCallback(() => {
    setState((current) => ({
      ...current,
      summoned: true,
      focus: current.focus + 1,
      raised: current.raised + 1,
    }));
  }, []);

  const value = useMemo<CreateBarStateValue>(
    () => ({
      ...state,
      target: routeProject ?? sceneProject ?? movieProject ?? state.project,
      onProject: routeProject !== null || sceneProject !== null || movieProject !== null,
      scene: routeScene,
      shown: opened === null || state.summoned,
      overViewer: opened !== null,
      summon,
      dismiss,
      setPrompt,
      setModel,
      setParams,
      setProject,
      setRole,
      detach,
      swapFrames,
      move,
      sent,
    }),
    [
      state,
      routeProject,
      routeScene,
      sceneProject,
      movieProject,
      opened,
      summon,
      dismiss,
      setPrompt,
      setModel,
      setParams,
      setProject,
      setRole,
      detach,
      swapFrames,
      move,
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
