import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Spinner, Text, Button } from "@ansavva/design-system";

import { deleteNodes, describeNode, renameNode } from "../apis/studio";
import { ReferenceFields } from "../components/character/ReferenceFields";
import type { Crumb } from "../components/layout/PageBar";
import { MediaPlayer, type MediaPlayerControls } from "../components/media/MediaPlayer";
import { TextPage } from "../components/text/TextPage";
import { DescribePanel } from "../components/viewer/DescribePanel";
import { Filmstrip } from "../components/viewer/Filmstrip";
import { ObjectActions } from "../components/viewer/ObjectActions";
import { ObjectDetails, ObjectHeader } from "../components/viewer/ObjectHeader";
import { OwnerLink } from "../components/viewer/OwnerLink";
import { useKeyboardNav } from "../hooks/useKeyboardNav";
import { useViewerFeed } from "../hooks/useViewerFeed";
import { DEFAULT_SORT, isSortOrder, type FileEntry, type SortOrder } from "../types";
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

  /**
   * The player's own container and controls, held in state rather than in refs.
   *
   * The container is what `Dialog.Root`'s `container` needs — the parts read it
   * WHILE RENDERING, so a ref filled by the same commit is still null on the
   * render that mounts them. The controls are how Space, `m` and `f` reach a
   * player that owns its own playback state. Both arrive through callbacks that
   * fire once; neither re-renders on a scrub.
   */
  const [stage, setStage] = useState<HTMLElement | null>(null);
  const [controls, setControls] = useState<MediaPlayerControls | null>(null);

  /**
   * Closed by default.
   *
   * **The describing pass is one of the things this rework gives up.** In the
   * reel the panel stayed open as the column scrolled, so captioning ten clips
   * was one press and nine flicks. On a page it is one file at a time, and the
   * panel takes the column beside the player rather than covering it.
   */
  const [describing, setDescribing] = useState(false);

  const items = feed.items;
  const found = items.findIndex((item) => item.id === nodeId);
  const index = found < 0 ? 0 : found;
  const current: FileEntry | undefined = items[index];

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
   * feed from the start" — see `feedPath` — and carries no id at all until the
   * first page lands. And an id the feed does not hold is a dead link, which
   * opens on the first file rather than on nothing. Either way the URL has to
   * name what is being shown, or Back and a copied link both lie.
   */
  useEffect(() => {
    if (current && current.id !== nodeId) setCurrent(current);
  }, [current, nodeId, setCurrent]);

  // Page ahead before the strip runs out, the way the reel did from its scroll
  // position. Only the recursive feed pages at all; the rest are exhausted on
  // arrival and `loadMore` is undefined.
  const { exhausted, loadMore } = feed;
  useEffect(() => {
    if (!exhausted && index >= items.length - PREFETCH_MARGIN) loadMore?.();
  }, [exhausted, index, items.length, loadMore]);

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
   */
  useKeyboardNav({
    onPrev: isText ? undefined : () => step(-1),
    onNext: isText ? undefined : () => step(1),
    onClose: isText ? undefined : close,
    onTogglePlay: controls ? () => controls.togglePlay() : undefined,
    onToggleMuted: controls ? () => controls.toggleMuted() : undefined,
    onToggleFullscreen: controls ? () => controls.toggleFullscreen() : undefined,
  });

  if (open && isText) {
    return <TextPage file={open} onClose={close} onSaved={feed.reload} />;
  }

  if (!current) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
        {feed.loading ? (
          <Spinner size="lg" label="Loading media" />
        ) : (
          <>
            <Text variant="body" tone="muted">
              No images or videos here.
            </Text>
            <Button size="sm" onClick={close}>
              Back
            </Button>
          </>
        )}
      </div>
    );
  }

  const isVideo = current.kind === "video";
  const position = `${index + 1}${
    feed.exhausted ? ` of ${items.length}${feed.truncated ? "+" : ""}` : ""
  }`;

  const renameThis = (name: string) => rename(current, name);
  const removeThis = () => remove(current);

  return (
    <>
      <ObjectHeader
        file={current}
        position={position}
        crumbs={crumbsFor(source)}
        container={stage}
        onRename={renameThis}
        onDelete={removeThis}
        describing={describing}
        onToggleDescribing={() => setDescribing((up) => !up)}
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
            // Rename and delete, and only those two. They have to be reachable
            // while the player is fullscreen, where the header below is not
            // painted; everything else on the header is a thing you do with the
            // page in front of you.
            actions={
              <ObjectActions
                file={current}
                variant="media"
                container={stage}
                onRename={renameThis}
                onDelete={removeThis}
              />
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
          {describing ? (
            <DescribePanel
              // Remounted per file so a caption typed on one cannot be carried
              // onto the next by a step.
              key={current.id}
              file={current}
              onSave={(changes) => describe(current, changes)}
              onClose={() => setDescribing(false)}
              // Only in a character's reference pool. Elsewhere a node has no
              // group, no position and no caption, and the panel is the file's
              // own fields alone.
              extra={
                source?.in === "refs" ? (
                  <ReferenceFields
                    characterId={source.id}
                    node={current.id}
                    onChanged={feed.reload}
                  />
                ) : undefined
              }
            />
          ) : (
            <ObjectDetails
              file={current}
              // A link that arrived with no context: say what the file belongs
              // to and offer the way there. Everywhere else the crumb above
              // already says it.
              aside={source === null ? <OwnerLink nodeId={current.id} /> : undefined}
            />
          )}
        </aside>
      </div>
    </>
  );
}

/**
 * The one crumb the address can honestly draw.
 *
 * A run is missing on purpose, for the reason `home` gives: `runPath` needs the
 * project id as well and a context carries one id. Home is always valid and the
 * breadcrumb from there is one click.
 */
function crumbsFor(source: ReturnType<typeof sourceFromParam>): Crumb[] | undefined {
  if (!source) return undefined;
  switch (source.in) {
    case "f":
    case "recursive":
      return [{ label: "Folder", to: folderPath(source.id) }];
    case "scene":
      return [{ label: "Scene", to: scenePath(source.id) }];
    case "refs":
      return [{ label: "Character", to: characterPath(source.id) }];
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
