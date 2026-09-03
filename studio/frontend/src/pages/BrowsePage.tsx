import { useCallback, useMemo, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import {
  FolderBrowser,
  type BrowserNav,
} from "../components/browse/FolderBrowser";
import { PageBar, type Crumb } from "../components/layout/PageBar";
import {
  DEFAULT_SORT,
  isSortOrder,
  type Crumb as FolderCrumb,
  type FileEntry,
  type SortOrder,
} from "../types";
import {
  folderPath,
  objectPath,
  sourceParam,
  targetFromPath,
  type FolderId,
} from "../utils/location";

/**
 * The library's file browser, at `/f` and `/f/<node_id>`.
 *
 * **The URL is the state.** Nothing here mirrors the location into component
 * state: doing so is what makes browser back and a pasted link disagree, and
 * both have to work for a share link to mean anything. That is the whole of what
 * this page is — the listing, the selection and the uploads live in
 * `FolderBrowser`, which a character's and a project's Files tab render too.
 *
 * **`/o/` is not this page any more.** It used to be: an object address
 * rendered this browser with the file open over it, which is why opening a run
 * output landed you in the file tree. Opening a file is a navigation to
 * `ViewerPage` now, and this page's job stops at the folder.
 *
 * **A `PageBar` now sits above it, and `FolderBrowser`'s own trail does not.**
 * The route names a folder, so the page frame every other screen carries — the
 * ancestry as crumbs, the current folder as the title — belongs here too. The
 * ancestry itself is `FolderBrowser`'s own `getFolder` answer, handed up
 * through `onBreadcrumbs` rather than fetched a second time for the page bar
 * to draw.
 */
export function BrowsePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [trail, setTrail] = useState<FolderCrumb[]>([]);

  const folder = useMemo(() => {
    const target = targetFromPath(location.pathname);
    return target.kind === "folder" ? target.id : null;
  }, [location.pathname]);

  const sortParam = params.get("sort");
  const sort: SortOrder = isSortOrder(sortParam) ? sortParam : DEFAULT_SORT;

  const setSort = useCallback(
    (next: SortOrder) => {
      const nextParams = new URLSearchParams(params);
      if (next === DEFAULT_SORT) nextParams.delete("sort");
      else nextParams.set("sort", next);
      setParams(nextParams, { replace: true });
    },
    [params, setParams],
  );

  /**
   * `replace` is for the one navigation that is not a journey: leaving a folder
   * because it no longer exists. Pushing there would leave the deleted folder as
   * the entry behind you, so back would load an empty listing of something you
   * just destroyed. Every other move between folders is a real history entry,
   * because the browser's back button has to retrace browsing.
   */
  const goToFolder = useCallback(
    (nextId: FolderId, { replace = false }: { replace?: boolean } = {}) => {
      navigate(
        { pathname: folderPath(nextId), search: location.search },
        { replace },
      );
    },
    [location.search, navigate],
  );

  const nav: BrowserNav = useMemo(
    () => ({
      folder,
      sort,
      setSort,
      goToFolder,
      // The sort rides along into the viewer so its sequence is the order the
      // grid was showing. Anything else means clicking the third tile and
      // arriving somewhere else in the reel.
      //
      // `deep` says whether the listing was a readdir or a search of the branch,
      // which decides which of the two the viewer re-reads — see
      // `BrowserNav.openFile`.
      openFile: (file: FileEntry, deep = false) => {
        navigate({
          pathname: objectPath(file.id),
          search: viewerSearch(folder, sort, deep),
        });
      },
      // The same address `openFile` navigates to, spelled out — an `href` is
      // what makes command-click work, and it has to agree with the handler or
      // the two gestures land in different places. One builder, so they cannot
      // disagree.
      fileHref: (file: FileEntry, deep = false) =>
        `${objectPath(file.id)}?${viewerSearch(folder, sort, deep)}`,
    }),
    [folder, goToFolder, navigate, sort, setSort],
  );

  // The first crumb is always the library root, and it is stored under `/`
  // rather than under a name worth showing — `FolderBrowser`'s own trail
  // spells that the same way for the standalone browser. Every level after it
  // reads its stored name; the last one is the title rather than a crumb, so
  // the current folder is never listed as a step to itself.
  const crumbs: Crumb[] = trail.slice(0, -1).map((crumb, index) => ({
    label: index === 0 ? "Files" : crumb.name,
    to: index === 0 ? folderPath(null) : folderPath(crumb.id),
  }));
  const title = trail.length <= 1 ? "Files" : (trail.at(-1)?.name ?? "Files");

  return (
    <>
      <PageBar crumbs={crumbs} title={title} />
      <FolderBrowser nav={nav} showTrail={false} onBreadcrumbs={setTrail} />
    </>
  );
}

/**
 * The viewer's query string: what it is scrolling through, and in what order.
 *
 * `recursive:` when the listing that was on screen searched the branch — the
 * Media view, or a tag filter — because that is the walk holding the file that
 * was clicked. `f:` is the readdir, and a deep tile addressed with it named a
 * folder that mostly does not contain it.
 */
function viewerSearch(folder: FolderId, sort: SortOrder, deep: boolean): string {
  const search = new URLSearchParams({
    in: sourceParam({ in: deep ? "recursive" : "f", id: folder }),
  });
  if (sort !== DEFAULT_SORT) search.set("sort", sort);
  return search.toString();
}
