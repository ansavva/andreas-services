import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Drawer, Button, IconButton, Text } from "@ansavva/design-system";

import { EmptyState } from "../components/common/EmptyState";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  CloseIcon,
  CompareIcon,
} from "../components/common/icons";
import { LoadError } from "../components/common/LoadError";
import { PageLoading } from "../components/common/PageLoading";
import {
  deleteNodes,
  describeNode,
  getCharacter,
  getNode,
  getScene,
  renameNode,
} from "../apis/studio";
import { PageBar, type Crumb } from "../components/layout/PageBar";
import { CompareStage } from "../components/media/CompareStage";
import { MediaPlayer, type MediaPlayerControls } from "../components/media/MediaPlayer";
import { TextPage } from "../components/text/TextPage";
import { FileDetailsPanel } from "../components/viewer/FileDetailsPanel";
import { Filmstrip } from "../components/viewer/Filmstrip";
import { ObjectActions } from "../components/viewer/ObjectActions";
import { ObjectControls, ObjectDetails } from "../components/viewer/ObjectAside";
import { OwnerLink } from "../components/viewer/OwnerLink";
import { ViewerFrame } from "../components/viewer/ViewerFrame";
import { useCreateBar } from "../context/CreateBarContext";
import { useKeyboardNav } from "../hooks/useKeyboardNav";
import { useResource } from "../hooks/useResource";
import { useViewerFeed } from "../hooks/useViewerFeed";
import { DEFAULT_SORT, isSortOrder, type FileEntry, type SortOrder } from "../types";
import { formatBytes } from "../utils/format";
import type { ViewerSource } from "../utils/location";
import {
  FAVORITES_PATH,
  HOME_PATH,
  characterPath,
  folderPath,
  objectPath,
  scenePath,
  sourceFromParam,
} from "../utils/location";

/** Fetch the next page this many files from the end of what is loaded. */
const PREFETCH_MARGIN = 4;

/**
 * One file, open, with whatever it sits among.
 *
 * **The same viewer the opened run gets.** `/o/<id>` has been three things: a
 * `fixed inset-x-0 z-50` reel of full-viewport panes with its own chrome, then
 * an ordinary page with a `PageBar` and a player capped at `65dvh` in the
 * content column, and now this — `ViewerFrame`, the box `RunLightbox` draws
 * in, with the picture on the stage taking every pixel between the header
 * and the create sheet's handle, the file's own words in a rail beside it,
 * and the feed's neighbours down the right edge. The page form put a
 * two-thirds-height picture beside a column of facts and read as a form with
 * a preview; the opened run's picture was twice the size, and this is the
 * same thing, so it is the same box.
 *
 * What survives from the page form is everything that made it a *page*: the
 * crumb saying where the file sits (at the top of the rail now), the
 * address, and the create sheet staying out of the way until something calls
 * it up — `CreateBarContext` treats `/o/<id>` as it treats the opened run.
 *
 * **`ViewerPage` was the name, and everything below the body is unchanged from
 * it.** `useViewerFeed` still decides what the neighbours are from `?in=`; the
 * address is still rewritten with `replace` rather than pushed; closing still
 * undoes the entry that opened it, or navigates when there is none; and a text
 * file still gets `TextPage`. Those four were separately debugged and none of
 * them was about the reel.
 *
 * What did not change either is the address's durable half. `/o/<id>` alone
 * still opens the file, because the id is the share link and `?in=` is a
 * convenience for whoever is browsing. A link that has lost its context shows
 * the file on its own and offers the way back to whatever owns it.
 */
export function ObjectPage() {
  const { nodeId = "" } = useParams();
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();

  const source = useMemo(() => sourceFromParam(params.get("in")), [params]);
  const sortParam = params.get("sort");
  const sort: SortOrder = isSortOrder(sortParam) ? sortParam : DEFAULT_SORT;

  const feed = useViewerFeed(source, nodeId, sort);
  const crumbs = useSourceCrumbs(source);
  const bar = useCreateBar();

  /**
   * The player's own container and controls, held in state rather than in refs.
   *
   * The container is what `Drawer.Root`'s `container` needs — the parts read it
   * WHILE RENDERING, so a ref filled by the same commit is still null on the
   * render that mounts them. The controls are how Space, `m` and `f` reach a
   * player that owns its own playback state. Both arrive through callbacks that
   * fire once; neither re-renders on a scrub.
   */
  const [stage, setStage] = useState<HTMLElement | null>(null);
  const [controls, setControls] = useState<MediaPlayerControls | null>(null);

  /**
   * Closed by default, and a drawer when it is open.
   *
   * **The describing pass is one of the things this rework gives up.** In the
   * reel the panel stayed open as the column scrolled, so captioning ten clips
   * was one press and nine flicks. On a page it is one file at a time.
   *
   * **It used to replace the details column, and rename was a second surface
   * beside it.** One drawer holds all three of the file's own fields now: two
   * controls that opened two overlays to edit one row told a reader nothing
   * about which to press, and the column swap meant the read-only details
   * vanished exactly while they were being edited.
   */
  const [editing, setEditing] = useState(false);

  /**
   * Whether the drawer holds unsaved words, and whether a dismissal was refused.
   *
   * A ref rather than state, because the dismissal handler reads it and nothing
   * renders from it — `RunPage` carries the promote drawer's the same way, and
   * the panel is careful to report it through a ref of its own.
   */
  const editDirty = useRef(false);
  const [editWarning, setEditWarning] = useState(false);

  /**
   * Whether the player owns the screen, because that decides where the drawer
   * is mounted.
   *
   * **It is aimed at the player ONLY while the player is fullscreen**, and that
   * qualifier is the whole point. Anything portalled to `<body>` is mounted,
   * focusable and unpainted while a frame fills the screen, so a drawer opened
   * from the chrome over the media has to be a descendant of the fullscreen
   * element — the reason the rename dialog this absorbed carried a `container`.
   * Aiming it there *unconditionally* is the version that was tried first and
   * looked broken: the player's box is `isolate`, so a panel inside it is
   * z-ordered within that stacking context and the app header paints straight
   * over its top edge. `position: fixed` still measured against the viewport
   * throughout — it is stacking, not geometry, and only the fullscreen case
   * needs the container to pay for it.
   */
  const [fullscreen, setFullscreen] = useState(false);
  useEffect(() => {
    // `Boolean(...)`, not `!== null`: jsdom defines no `fullscreenElement` at
    // all, and the strict comparison reads `undefined` as "yes, fullscreen".
    const sync = () => setFullscreen(Boolean(document.fullscreenElement));
    sync();
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  /**
   * Compare: the open file pinned as A, and the neighbour beside it as B.
   *
   * `null` is "not comparing"; `{ a, b: null }` is comparing with the right
   * pane empty. While comparing, a press on the strip and a Left/Right both
   * choose B rather than stepping the address — the open file stays where it
   * is, which is what "pinned" means. `a` records which file was pinned, so
   * the address moving on (Close, a crumb, a delete) leaves the comparison
   * behind without an effect to clear it — and a swap, which moves the
   * address deliberately, pins the new one in the same write.
   */
  const [pinned, setPinned] = useState<{ a: string; b: FileEntry | null } | null>(null);
  const compare = pinned && pinned.a === nodeId ? pinned : null;
  const setCompare = useCallback(
    (b: FileEntry | null) => setPinned({ a: nodeId, b }),
    [nodeId],
  );

  const items = feed.items;
  const { exhausted, loadMore } = feed;
  const found = items.findIndex((item) => item.id === nodeId);
  const index = found < 0 ? 0 : found;

  /**
   * The address names a file this feed has not produced — *yet*.
   *
   * A recursive context is paged, so page one holding no match means "keep
   * looking", not "dead link". Until the walk runs out, this screen is still
   * loading: substituting `items[0]` here is what turns one wrong guess into a
   * rewritten address and a file nobody asked for on screen.
   */
  const searching = found < 0 && nodeId !== "" && !exhausted;
  const current: FileEntry | undefined = searching ? undefined : items[index];

  /**
   * Where "out" goes.
   *
   * Back, when there is somewhere to go back to: opening pushed an entry, so
   * closing should undo it rather than pushing a second one — otherwise
   * open-then-close leaves a trail of the same folder, one per file looked at.
   * A cold share link has no entry to undo (`location.key` is React Router's
   * `"default"` for the first entry in a session), and stepping back from there
   * leaves the app entirely, so that case navigates to whatever the context
   * names.
   */
  const close = useCallback(() => {
    if (location.key !== "default") {
      navigate(-1);
      return;
    }
    navigate(home(source), { replace: true });
  }, [location.key, navigate, source]);

  /**
   * Stepping rewrites the address rather than pushing to it.
   *
   * Twenty files walked past would otherwise be twenty back-presses to escape.
   * The context rides along so the link stays as good as the one that was
   * opened.
   */
  const setCurrent = useCallback(
    (file: FileEntry) => {
      navigate(objectPath(file.id, source), { replace: true });
    },
    [navigate, source],
  );

  /**
   * The address adopts the file actually on screen.
   *
   * Two cases reach here and they want the same answer. `/o?in=…` is "play this
   * feed from the start" and carries no id at all until the first page lands.
   * And an id the *exhausted* feed does not hold is a dead link, which opens on
   * the first file rather than on nothing. Either way the URL has to name what
   * is being shown, or Back and a copied link both lie.
   *
   * **Exhausted is the load-bearing word**, and leaving it out is the bug this
   * carries: a paged feed whose first page happens not to hold the file is not a
   * dead link, and adopting `items[0]` there rewrote the address to a file
   * nobody clicked. `searching` is that state, and it leaves `current`
   * undefined, so this cannot fire during it.
   */
  useEffect(() => {
    if (current && current.id !== nodeId) setCurrent(current);
  }, [current, nodeId, setCurrent]);

  // Page ahead before the strip runs out, the way the reel did from its scroll
  // position. Only the recursive feed pages at all; the rest are exhausted on
  // arrival and `loadMore` is undefined.
  //
  // `searching` pages for a different reason: the file the address names is
  // somewhere further into the walk, and every page is one more chance to reach
  // it. It terminates either way — at the match, or at the end of the branch.
  useEffect(() => {
    if (exhausted) return;
    if (searching || index >= items.length - PREFETCH_MARGIN) loadMore?.();
  }, [exhausted, index, items.length, loadMore, searching]);

  const describe = useCallback(
    async (file: FileEntry, changes: { description?: string | null; tags?: string[] | null }) => {
      await describeNode(file.id, changes);
      feed.reload();
    },
    [feed],
  );

  const rename = useCallback(
    async (file: FileEntry, name: string) => {
      await renameNode(file.id, name);
      feed.reload();
    },
    [feed],
  );

  /**
   * Delete, then step out.
   *
   * The file cannot stay — its bytes are gone — and advancing to the next one on
   * its own is how the wrong thing gets deleted twice, so this leaves rather
   * than stepping. `replace`, because the address it is leaving names something
   * that no longer exists and should not be one back-press away.
   */
  const remove = useCallback(
    async (file: FileEntry) => {
      await deleteNodes([file.id]);
      navigate(home(source), { replace: true });
    },
    [navigate, source],
  );

  const step = useCallback(
    (delta: number) => {
      // Comparing: the step chooses B, from wherever B is — or from the open
      // file, when nothing is beside it yet.
      if (compare) {
        const from = compare.b ? items.findIndex((item) => item.id === compare.b?.id) : index;
        const next = items[from + delta];
        if (next && next.id !== nodeId && next.kind === "image") setCompare(next);
        return;
      }
      const next = items[index + delta];
      if (next) setCurrent(next);
    },
    [compare, index, items, nodeId, setCompare, setCurrent],
  );

  /** A press on the strip: the file to open, or — while comparing — B. */
  const pick = useCallback(
    (file: FileEntry) => {
      if (!compare) {
        setCurrent(file);
        return;
      }
      if (file.id === nodeId || file.kind !== "image") return;
      setCompare(file);
    },
    [compare, nodeId, setCompare, setCurrent],
  );

  /**
   * A text file gets the code viewer, not the player.
   *
   * `/o/<id>` has always been the address of a `prompt.json` or a `profile.yaml`
   * as well as of a frame — the browser used to branch on it inline, and this
   * screen inherits that. It reads from `all` rather than `items` because a
   * filmstrip of a YAML file is nothing, so the sequence deliberately excludes
   * it.
   */
  const open = feed.all.find((item) => item.id === nodeId);
  const isText = Boolean(open && open.kind !== "image" && open.kind !== "video");

  /**
   * ←/→ walk the feed; Space, `m` and `f` are the player's.
   *
   * **Escape is handed over entirely while a text file is open.** `TextPage`
   * binds its own, and two listeners calling the same `close` is `navigate(-1)`
   * twice — one press leaving two screens.
   *
   * **The details drawer takes the whole keyboard for the same reason.** It
   * binds Escape itself, so leaving these bound would make one press a
   * dismissal *and* a `navigate(-1)` — and a form that declined the dismissal
   * would lose its words to the page behind it anyway. It is modal, so stepping
   * the feed underneath it is wrong whatever the key does.
   */
  const modal = editing;
  useKeyboardNav({
    onPrev: isText || modal ? undefined : () => step(-1),
    onNext: isText || modal ? undefined : () => step(1),
    onClose: isText || modal ? undefined : close,
    onTogglePlay: controls && !modal ? () => controls.togglePlay() : undefined,
    onToggleMuted: controls && !modal ? () => controls.toggleMuted() : undefined,
    onToggleFullscreen:
      controls && !modal ? () => controls.toggleFullscreen() : undefined,
    onZoomIn: controls && !modal ? () => controls.zoomIn() : undefined,
    onZoomOut: controls && !modal ? () => controls.zoomOut() : undefined,
    onZoomReset: controls && !modal ? () => controls.zoomReset() : undefined,
  });

  if (open && isText) {
    // Same crumb the media case draws — `TextPage` grew its own `PageBar`
    // once it stopped being a `fixed inset-0` takeover, and a page inside
    // `AppLayout` needs to say where it sits like every other one.
    return <TextPage file={open} onClose={close} onSaved={feed.reload} crumbs={crumbs} />;
  }

  if (!current) {
    // A feed that failed used to look exactly like a feed that was empty —
    // the error was never read — so a dropped connection said "no images or
    // videos here" about a folder full of them.
    if (feed.error) {
      return (
        <LoadError
          what="this file"
          message={feed.error}
          onRetry={feed.reload}
          escape={{ label: "Back", onClick: close }}
        />
      );
    }
    // `searching` as well as `loading`: between two pages of a walk that has
    // not found the file yet, nothing is in flight and the feed is not empty —
    // saying "no images or videos yet" there would be a verdict delivered
    // mid-search.
    if (feed.loading || searching) return <PageLoading label="Loading media" />;
    return (
      <EmptyState
        title="No images or videos yet."
        action={
          <Button size="sm" onClick={close}>
            Back
          </Button>
        }
      />
    );
  }

  const isVideo = current.kind === "video";
  const position = `${index + 1}${
    feed.exhausted ? ` of ${items.length}${feed.truncated ? "+" : ""}` : ""
  }`;

  const renameThis = (name: string) => rename(current, name);
  const removeThis = () => remove(current);

  /**
   * The open picture, attached to the create bar as a reference.
   *
   * **A still only.** A reference is a picture; a clip attached as one is sent
   * to a field that refuses it, which is the rule `OutputTile` and the run's
   * rail already carry. The bar's own picker walks the same tree, so this is a
   * shortcut rather than a second way in — but it is the shortcut from the one
   * place a person is already looking at the picture they want.
   */
  const attachAsReference = isVideo
    ? undefined
    : () =>
        bar.attach(
          { node: current.id, url: current.url, name: current.name, kind: "object" },
          "reference",
        );

  /**
   * Every way of putting the drawer away asks the form first.
   *
   * The backdrop, Escape and the panel's own Close all arrive here, so a form
   * holding typed words declines all three the same way rather than declining
   * the accidental ones and honouring the deliberate one — a press of "Close" is
   * not a decision to throw a description away either.
   */
  const askToClose = () => {
    if (editDirty.current) {
      setEditWarning(true);
      return;
    }
    setEditWarning(false);
    setEditing(false);
  };
  const toggleEditing = () => (editing ? askToClose() : setEditing(true));

  /**
   * A and B change places: B becomes the open file, A goes beside it. The
   * address follows A, as it always does.
   */
  const swap = () => {
    if (!compare?.b) return;
    setPinned({ a: compare.b.id, b: current });
    setCurrent(compare.b);
  };

  const canCompare = !isVideo && items.length > 1;
  const stepPrev = index > 0 || (compare !== null && compare.b !== null);
  const stepNext = index < items.length - 1 || (compare !== null && compare.b !== null);

  return (
    <ViewerFrame aria-label="File" data-testid="object-viewer">
      {/* The stage: the picture large, with the neighbours' steps at its
          sides from `md` and the strip carrying them below it. The same
          shape as the opened run's, for the same reasons `RunLightbox`
          gives at each of these. */}
      <div className="relative flex min-h-[80dvh] min-w-0 flex-1 flex-col md:min-h-0">
        <div className="absolute right-3 top-3 z-10 flex gap-1">
          {canCompare && (
            <IconButton
              label={compare ? "Stop comparing" : "Compare"}
              size="sm"
              intent="overlay"
              pressed={compare !== null}
              onClick={() => (compare ? setPinned(null) : setCompare(null))}
              className=""
            >
              <CompareIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
            </IconButton>
          )}
          <IconButton
            label="Close (Esc)"
            size="sm"
            intent="overlay"
            onClick={close}
            className=""
          >
            <CloseIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
          </IconButton>
        </div>
        {stepPrev && (
          <IconButton
            label="Previous file (←)"
            size="sm"
            intent="overlay"
            onClick={() => step(-1)}
            className="absolute left-3 top-1/2 z-10 hidden -translate-y-1/2 md:flex"
          >
            <ChevronLeftIcon className="size-5 fill-none stroke-current stroke-[1.5]" />
          </IconButton>
        )}
        {stepNext && (
          <IconButton
            label="Next file (→)"
            size="sm"
            intent="overlay"
            onClick={() => step(1)}
            className="absolute right-3 top-1/2 z-10 hidden -translate-y-1/2 md:flex"
          >
            <ChevronRightIcon className="size-5 fill-none stroke-current stroke-[1.5]" />
          </IconButton>
        )}

        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 p-2 pt-12 md:p-8">
          {compare ? (
            <CompareStage
              a={{ node: current.id, url: current.url, name: current.name, size: current.size }}
              b={
                compare.b
                  ? { node: compare.b.id, url: compare.b.url, name: compare.b.name, size: compare.b.size }
                  : null
              }
              onSwap={swap}
              onControlsChange={setControls}
            />
          ) : (
            <>
              <div className="min-h-0 w-full flex-1">
                {/*
                  Not keyed on the node, deliberately: stepping from one clip
                  to the next keeps the player mounted and playing, which is
                  the one thing the reel's column did better than a lightbox
                  ever has. The zoom resets itself on the node.
                */}
                <MediaPlayer
                  nodeId={current.id}
                  url={current.url}
                  name={current.name}
                  isVideo={isVideo}
                  aspect="auto"
                  zoomable
                  className="h-full w-full border border-line"
                  onContainerChange={setStage}
                  onControlsChange={setControls}
                  // **Only while fullscreen.** The rail carries Copy, Edit,
                  // Download and Close — the same controls this row used to
                  // duplicate over the media on every visit — so drawing it
                  // too is two rows saying the same thing. Fullscreen is the
                  // one state where the rail genuinely is not painted, and
                  // edit/delete are the two that still have to be reachable
                  // there.
                  actions={
                    fullscreen ? (
                      <ObjectActions
                        file={current}
                        variant="media"
                        onDelete={removeThis}
                        editing={editing}
                        onToggleEditing={toggleEditing}
                      />
                    ) : undefined
                  }
                />
              </div>
              <Text variant="caption" family="mono" tone="muted" className="tabular-nums">
                {current.name} · {formatBytes(current.size)}
              </Text>
            </>
          )}
        </div>
      </div>

      {/* The rail: where the file sits, what can be done to it, and what it
          says about itself. */}
      <aside
        aria-label="File"
        className="flex w-full shrink-0 flex-col gap-4 border-t border-line bg-bg p-5 md:w-[360px] md:overflow-y-auto md:border-l md:border-t-0"
      >
        {/*
          Crumbs and nothing else. What a bar can say that the column cannot
          is where the page sits.
        */}
        <PageBar crumbs={crumbs} />

        <ObjectControls
          file={current}
          position={position}
          onDelete={removeThis}
          editing={editing}
          onToggleEditing={toggleEditing}
          onUseAsReference={attachAsReference}
        />

        <ObjectDetails
          file={current}
          // A link that arrived with no context: say what the file belongs
          // to and offer the way there. Everywhere else the crumb above
          // already says it.
          aside={source === null ? <OwnerLink nodeId={current.id} /> : undefined}
        />
      </aside>

      {/* The neighbours, last in the flex — a row along the foot below `md`,
          a column down the right edge above it. See `RunStrip`. */}
      <Filmstrip
        items={items}
        currentId={current.id}
        compareId={compare ? (compare.b?.id ?? null) : null}
        loading={feed.loading}
        onSelect={pick}
        onPrev={stepPrev ? () => step(-1) : undefined}
        onNext={stepNext ? () => step(1) : undefined}
      />

      {editing && (
        /*
          **The editor is a drawer over the page, and over the frame while the
          frame owns the screen.** See `fullscreen` above for why the container
          is conditional rather than simply the player.
        */
        <Drawer.Root
          open
          container={fullscreen ? stage : null}
          onOpenChange={(next: boolean) => {
            if (next) return;
            // The backdrop and Escape both arrive here, and both go through the
            // one refusal — see `askToClose`.
            askToClose();
          }}
        >
          <Drawer.Backdrop />
          <Drawer.Panel className="w-full max-w-md overflow-y-auto">
            <FileDetailsPanel
              // Remounted per file so a name or caption typed on one cannot be
              // carried onto the next by a step.
              key={current.id}
              file={current}
              onSave={(changes) => describe(current, changes)}
              onRename={renameThis}
              onClose={askToClose}
              onDirtyChange={(dirty) => {
                editDirty.current = dirty;
                if (!dirty) setEditWarning(false);
              }}
              unsavedWarning={editWarning}
              onDiscard={() => {
                editDirty.current = false;
                setEditWarning(false);
                setEditing(false);
              }}
              onKeepEditing={() => setEditWarning(false)}
              // **No second panel any more.** A `ReferenceFields` used to sit
              // here when the node was in a character's reference pool, editing
              // the group, the position and a caption that lived on the `REF#`
              // row. All three are the file's own `tags` and `description` now,
              // which the panel below already edits — so the second form was a
              // second way to say the same thing about the same file.
            />
          </Drawer.Panel>
        </Drawer.Root>
      )}
    </ViewerFrame>
  );
}

/**
 * The one crumb the address can honestly draw — named, not generic.
 *
 * **This used to say "Folder", "Scene" or "Character" no matter which one it
 * was**, which told a reader where the KIND of place was and never which
 * place. The label is the entity's own name now, fetched by the id the
 * context already carries — `getNode`, `getScene` or `getCharacter`
 * depending on which source it is, called unconditionally in that order
 * because hooks cannot be called any other way, and idle (no query, no
 * request) for whichever two are not the source in hand.
 *
 * A run is still missing a crumb of its own, for the reason `home` below
 * gives: `runPath` needs the project id as well and a context carries one
 * id. Home is always valid and the breadcrumb from there is one click.
 *
 * The library root (`f`/`recursive` with no id) has no node to name — "Files"
 * is what it is called everywhere else in the app the address bar spells it
 * out (the header link, `BrowsePage`'s own title) — and a name still loading
 * falls back to the generic word for what it is, the same way
 * `useProjectCrumb` shows "Project" until the fetch lands.
 */
function useSourceCrumbs(source: ViewerSource | null): Crumb[] | undefined {
  const folderId = source && (source.in === "f" || source.in === "recursive") ? source.id : null;
  const sceneId = source?.in === "scene" ? source.id : null;
  const characterId = source?.in === "refs" ? source.id : null;

  const folder = useResource(
    folderId ? ["crumb-folder", folderId] : null,
    folderId ? () => getNode(folderId) : null,
  );
  const scene = useResource(
    sceneId ? ["crumb-scene", sceneId] : null,
    sceneId ? () => getScene(sceneId) : null,
  );
  const character = useResource(
    characterId ? ["crumb-character", characterId] : null,
    characterId ? () => getCharacter(characterId) : null,
  );

  if (!source) return undefined;
  switch (source.in) {
    case "f":
    case "recursive":
      return [
        {
          label: source.id === null ? "Files" : (folder.data?.name ?? "Folder"),
          to: folderPath(source.id),
        },
      ];
    case "scene":
      return [{ label: scene.data?.name ?? "Scene", to: scenePath(source.id) }];
    case "refs":
      return [{ label: character.data?.name ?? "Character", to: characterPath(source.id) }];
    // The one context whose crumb needs no fetch: it names no entity, so
    // there is nothing to look up and the label is the screen's own name.
    case "fav":
      return [{ label: "Favorites", to: FAVORITES_PATH }];
    case "run":
      return [{ label: "Home", to: HOME_PATH }];
  }
}

/**
 * The screen a context came from, for a close that has no history to undo.
 *
 * **A run lands on home, and that is a real gap rather than an oversight.** A
 * run's address is `/p/<project>/r/<run>` — it needs both ids — and a context
 * carries one. Putting the project in the parameter as well would make the
 * commonest link in the app longer to serve a case that only arises on a cold
 * share link into a run's output. Home is always valid; the breadcrumb from
 * there is one click.
 */
function home(source: ReturnType<typeof sourceFromParam>): string {
  if (!source) return HOME_PATH;
  switch (source.in) {
    case "f":
    case "recursive":
      return folderPath(source.id);
    case "scene":
      return scenePath(source.id);
    case "refs":
      return characterPath(source.id);
    case "fav":
      return FAVORITES_PATH;
    case "run":
      return HOME_PATH;
  }
}
