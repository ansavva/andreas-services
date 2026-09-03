import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Drawer, Button } from "@ansavva/design-system";

import { EmptyState } from "../components/common/EmptyState";
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
import type { Crumb } from "../components/layout/PageBar";
import { MediaPlayer, type MediaPlayerControls } from "../components/media/MediaPlayer";
import { TextPage } from "../components/text/TextPage";
import { FileDetailsPanel } from "../components/viewer/FileDetailsPanel";
import { Filmstrip } from "../components/viewer/Filmstrip";
import { ObjectActions } from "../components/viewer/ObjectActions";
import { ObjectDetails, ObjectHeader } from "../components/viewer/ObjectHeader";
import { OwnerLink } from "../components/viewer/OwnerLink";
import { useKeyboardNav } from "../hooks/useKeyboardNav";
import { useResource } from "../hooks/useResource";
import { useViewerFeed } from "../hooks/useViewerFeed";
import { DEFAULT_SORT, isSortOrder, type FileEntry, type SortOrder } from "../types";
import type { ViewerSource } from "../utils/location";
import {
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
 * **This is an ordinary page now, not an overlay.** `/o/<id>` was
 * `fixed inset-x-0 z-50` over a black shell — a vertical scroll-snap reel of
 * full-viewport panes with its own chrome, its own transport and its own idea
 * of what a header is. It is `AppLayout` with a `PageBar` on it like every
 * other screen: one `MediaPlayer` large in the content column, the file's own
 * words beside it, and the feed's neighbours as a filmstrip underneath. What
 * that buys is that a clip is a *thing with an address* rather than a mode you
 * enter and leave.
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
      const next = items[index + delta];
      if (next) setCurrent(next);
    },
    [index, items, setCurrent],
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
  });

  if (open && isText) {
    // Same crumb `ObjectHeader` draws for the media case — `TextPage` grew its
    // own `PageBar` once it stopped being a `fixed inset-0` takeover, and a
    // page inside `AppLayout` needs to say where it sits like every other one.
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
    // saying "no images or videos here" there would be a verdict delivered
    // mid-search.
    if (feed.loading || searching) return <PageLoading label="Loading media" />;
    return (
      <EmptyState
        title="No images or videos here."
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

  return (
    <>
      <ObjectHeader
        file={current}
        position={position}
        crumbs={crumbs}
        onDelete={removeThis}
        editing={editing}
        onToggleEditing={toggleEditing}
        onClose={close}
      />

      {/*
        One column on a phone, two from `lg`. The player leads in both, because
        it is what the address names — the words beside it on a wide screen sit
        under it on a narrow one rather than pushing the picture off the fold.
      */}
      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-6">
        <div className="flex min-w-0 flex-col gap-3">
          {/*
            Not keyed on the node, deliberately: stepping from one clip to the
            next keeps the player mounted and playing, which is the one thing
            the reel's column did better than a lightbox ever has.

            `100dvh` is what the height is measured against and never `inset-0`
            — the reel paid for that lesson and `MediaPlayer` carries it — so
            this cap tracks the browser's toolbars instead of hiding behind
            them.
          */}
          <MediaPlayer
            nodeId={current.id}
            url={current.url}
            name={current.name}
            isVideo={isVideo}
            aspect="auto"
            className="h-[min(65dvh,44rem)] border border-line"
            onContainerChange={setStage}
            onControlsChange={setControls}
            // **Only while fullscreen.** The page header carries Copy, Edit,
            // Download and Close now — the same controls this row used to
            // duplicate over the media on every visit — so drawing it too is
            // two rows saying the same thing. Fullscreen is the one state
            // where the header genuinely is not painted, and edit/delete are
            // the two that still have to be reachable there.
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

          <Filmstrip
            items={items}
            currentId={current.id}
            loading={feed.loading}
            onSelect={setCurrent}
            onPrev={index > 0 ? () => step(-1) : undefined}
            onNext={index < items.length - 1 ? () => step(1) : undefined}
          />
        </div>

        <aside className="flex min-w-0 flex-col gap-4">
          <ObjectDetails
            file={current}
            // A link that arrived with no context: say what the file belongs
            // to and offer the way there. Everywhere else the crumb above
            // already says it.
            aside={source === null ? <OwnerLink nodeId={current.id} /> : undefined}
          />
        </aside>
      </div>

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
    </>
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
    case "run":
      return HOME_PATH;
  }
}
