import { useCallback, useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { DEFAULT_SORT, isSortOrder, type FileEntry, type SortOrder } from "../../types";
import { objectPath, type FolderId } from "../../utils/location";
import { useSearchParamState } from "../../hooks/useSearchParamState";
import { FolderBrowser, type BrowserNav } from "./FolderBrowser";

/**
 * The browser as an entity's **Files** tab, split out of `FolderBrowser`.
 *
 * They are two different screens sharing one listing: the standalone browser
 * spends the address bar on the folder, and a tab cannot — the address is
 * already naming the character or the project it sits inside. That difference
 * is the whole reason `BrowserNav` is an interface, so the two implementations
 * of it belong in two files rather than one at the bottom of the other.
 *
 * Nothing here changed in the move.
 */

/**
 * A browser driven by component state rather than by the URL — the Files tab.
 *
 * The address bar is spent on the entity, so navigating a subfolder inside a tab
 * cannot touch it: doing so would replace the page you are standing on, and
 * browser-back out of three subfolders would walk back through a character page
 * three times.
 *
 * What is given up is that a folder inside a tab is not linkable. That is the
 * right trade in one direction only, and it is why `/f/<id>` still exists and the
 * tab does not replace it: a *link* to a folder is a link to the browser.
 */
export function useLocalBrowserNav(rootId: string, param = "folder"): BrowserNav {
  const navigate = useNavigate();
  const location = useLocation();
  // **Which query key, because a project draws TWO of these** — Files, and the
  // Runs tab's Grid. One key between them would carry a folder id from one
  // subtree into the other on a tab switch, leaving a browser standing
  // somewhere it cannot show. The default is the name Files has always used,
  // so its links still work.
  const [folderParam, setFolderParam] = useSearchParamState(param, "");
  // `fsort`, namespaced, because this shares a URL with the entity page's own
  // params (`tab`, and RunsTable's `status`/`character`/`model`/`since`) — a
  // bare `sort` would collide the moment either grows one.
  const [sortParam, setSortParam] = useSearchParamState("fsort", DEFAULT_SORT);
  const sort: SortOrder = isSortOrder(sortParam) ? sortParam : DEFAULT_SORT;

  // The entity's own root is the default, so it is written as absence — a
  // character's Files tab at rest is `?tab=files` and not `?tab=files&folder=…`.
  const folder = folderParam || rootId;

  /** A real address for a crumb — see `FolderBrowser`'s own trail. */
  const folderHref = useCallback(
    (id: FolderId) => {
      const params = new URLSearchParams(location.search);
      if (id === null || id === rootId) params.delete(param);
      else params.set(param, id);
      const query = params.toString();
      return query ? `${location.pathname}?${query}` : location.pathname;
    },
    [location.pathname, location.search, param, rootId],
  );

  return useMemo(
    () => ({
      folder,
      sort,
      setSort: setSortParam,
      goToFolder: (id: FolderId) => {
        // `null` is the *library* root, which a scoped browser has no way to
        // show and no business showing — the boundary crumb is this entity's
        // root, so that is where "up from the top" lands.
        setFolderParam(id === null || id === rootId ? "" : id);
      },
      folderHref,
      // **Opening a file leaves the tab, and that is the right trade now.** The
      // viewer is a screen with an address; keeping it inside the panel would
      // mean the one thing in this app most worth sending someone was the one
      // thing with no link. Back returns to the tab, at the folder it was on —
      // which is the half `?folder=` bought.
      //
      // `deep` picks which listing the viewer re-reads to find the neighbours —
      // see `BrowserNav.openFile`. It is the whole fix for a Media tile that
      // opened onto "No images or videos here".
      openFile: (file: FileEntry, deep = false) =>
        navigate(objectPath(file.id, { in: deep ? "recursive" : "f", id: folder })),
      fileHref: (file: FileEntry, deep = false) =>
        objectPath(file.id, { in: deep ? "recursive" : "f", id: folder }),
    }),
    [folder, folderHref, navigate, rootId, setFolderParam, setSortParam, sort],
  );
}

/**
 * The browser scoped to one entity's folder — a character's or a project's
 * **Files** tab.
 *
 * A component of its own so that the hook driving it is called at the top of
 * *something*: a tab panel renders nothing while it is inactive, so the state
 * belongs to the tab rather than to the page, and switching away genuinely
 * discards it.
 *
 * **The chip row above the browser is gone, not replaced.** A character's root
 * children each used to get a tab of their own, beside Profile and References
 * — a *listing* turned into navigation, which grew and shrank as folders were
 * created and deleted. That became a scrolling row of shortcut chips instead,
 * which was a second way up the same tree the browser already draws: three
 * stacked ways to say "where am I" (the chips, the browser's own
 * `← Back`-plus-trail, and this tab's boundary) for one folder. `FolderBrowser`
 * now draws that trail itself, as real breadcrumbs with real addresses, which
 * is the one place this belongs.
 */
export function FolderTab({
  rootId,
  label,
}: {
  rootId: string;
  /** The entity's name, for the boundary crumb — see `FolderBrowser`. */
  label?: string;
}) {
  const nav = useLocalBrowserNav(rootId);
  return <FolderBrowser nav={nav} boundary={rootId} boundaryLabel={label} />;
}
