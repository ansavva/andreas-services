import { useCallback, useMemo } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { deleteNodes, describeNode, renameNode } from "../apis/studio";
import { ReferenceFields } from "../components/character/ReferenceFields";
import { TextPage } from "../components/text/TextPage";
import { OwnerLink } from "../components/viewer/OwnerLink";
import { ReelView } from "../components/viewer/ReelView";
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

/**
 * One file, open, with whatever it sits among.
 *
 * **This is a screen now rather than an overlay on the browser.** `/o/<id>` used
 * to render `BrowsePage`, so opening a run's output resolved the file's parent
 * folder, fetched that listing, and left you in the file tree with the run gone
 * from the page. The address carries what you were looking through instead —
 * see `ViewerSource` — and the neighbours come from that.
 *
 * What did not change is the address's durable half. `/o/<id>` alone still
 * opens the file, because the id is the share link and `?in=` is a convenience
 * for whoever is browsing. A link that has lost its context shows the file on
 * its own and offers the way back to whatever owns it.
 */
export function ViewerPage() {
  const { nodeId = "" } = useParams();
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();

  const source = useMemo(() => sourceFromParam(params.get("in")), [params]);
  const sortParam = params.get("sort");
  const sort: SortOrder = isSortOrder(sortParam) ? sortParam : DEFAULT_SORT;

  const feed = useViewerFeed(source, nodeId, sort);

  const index = feed.items.findIndex((item) => item.id === nodeId);

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
   * Scrolling rewrites the address rather than pushing to it.
   *
   * Twenty clips scrolled past would otherwise be twenty back-presses to
   * escape. The context rides along so the link stays as good as the one that
   * was opened.
   */
  const setCurrent = useCallback(
    (file: FileEntry) => {
      navigate(objectPath(file.id, source), { replace: true });
    },
    [navigate, source],
  );

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
   * The pane cannot stay — its bytes are gone — and advancing to the next clip
   * on its own is how the wrong thing gets deleted twice, so this closes rather
   * than scrolling. `replace`, because the address it is leaving names something
   * that no longer exists and should not be one back-press away.
   */
  const remove = useCallback(
    async (file: FileEntry) => {
      await deleteNodes([file.id]);
      navigate(home(source), { replace: true });
    },
    [navigate, source],
  );

  /**
   * A text file gets the code viewer, not the reel.
   *
   * `/o/<id>` has always been the address of a `prompt.json` or a `profile.yaml`
   * as well as of a frame — the browser used to branch on it inline, and this
   * screen inherits that. It reads from `all` rather than `items` because a
   * reel of a YAML file is nothing, so the sequence deliberately excludes it.
   */
  const open = feed.all.find((item) => item.id === nodeId);
  if (open && open.kind !== "image" && open.kind !== "video") {
    return <TextPage file={open} onClose={close} onSaved={feed.reload} />;
  }

  return (
    <ReelView
      items={feed.items}
      loading={feed.loading}
      exhausted={feed.exhausted}
      truncated={feed.truncated}
      // A feed that has landed without the file in it is a dead link, which
      // `ReelView` says plainly rather than silently opening someone else's
      // frame. Until then `0` keeps the first pane on screen.
      startIndex={index < 0 ? 0 : index}
      onLoadMore={feed.loadMore}
      onClose={close}
      onCurrentChange={setCurrent}
      onRename={rename}
      onDelete={remove}
      onDescribe={describe}
      // A link that arrived with no context: say what the file belongs to and
      // offer the way there. Everywhere else the neighbours already say it.
      chromeAside={source === null ? (file) => <OwnerLink nodeId={file.id} /> : undefined}
      // Only in a character's reference pool. Elsewhere a node has no group, no
      // position and no caption, and the panel is the file's own fields alone.
      panelExtra={
        source?.in === "refs"
          ? (file) => (
              <ReferenceFields
                characterId={source.id}
                node={file.id}
                onChanged={feed.reload}
              />
            )
          : undefined
      }
    />
  );
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
