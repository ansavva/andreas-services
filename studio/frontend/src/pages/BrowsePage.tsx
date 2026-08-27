import { useCallback, useMemo } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { FolderBrowser, type BrowserNav } from "../components/browse/FolderBrowser";
import { DEFAULT_SORT, isSortOrder, type FileEntry, type SortOrder } from "../types";
import {
  feedPath,
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
 */
export function BrowsePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

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
      navigate({ pathname: folderPath(nextId), search: location.search }, { replace });
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
      openFile: (file: FileEntry) => {
        const search = new URLSearchParams({ in: sourceParam({ in: "f", id: folder }) });
        if (sort !== DEFAULT_SORT) search.set("sort", sort);
        navigate({ pathname: objectPath(file.id), search: search.toString() });
      },
      playReel: () => navigate(feedPath({ in: "recursive", id: folder })),
    }),
    [folder, goToFolder, navigate, sort, setSort],
  );

  return <FolderBrowser nav={nav} />;
}
