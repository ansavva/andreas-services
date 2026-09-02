import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getFolder } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { useSearchParamState } from "../../hooks/useSearchParamState";
import type { FileEntry, SortOrder } from "../../types";
import { objectPath, type FolderId } from "../../utils/location";
import { ChipRow } from "../common/ChipRow";
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
export function useLocalBrowserNav(rootId: string): BrowserNav {
  const navigate = useNavigate();
  const [folderParam, setFolderParam] = useSearchParamState("folder", "");
  const [sort, setSort] = useState<SortOrder>("newest");

  // The entity's own root is the default, so it is written as absence — a
  // character's Files tab at rest is `?tab=files` and not `?tab=files&folder=…`.
  const folder = folderParam || rootId;

  return useMemo(
    () => ({
      folder,
      sort,
      setSort,
      goToFolder: (id: FolderId) => {
        // `null` is the *library* root, which a scoped browser has no way to
        // show and no business showing — the boundary crumb is this entity's
        // root, so that is where "up from the top" lands.
        setFolderParam(id === null || id === rootId ? "" : id);
      },
      // **Opening a file leaves the tab, and that is the right trade now.** The
      // viewer is a screen with an address; keeping it inside the panel would
      // mean the one thing in this app most worth sending someone was the one
      // thing with no link. Back returns to the tab, at the folder it was on —
      // which is the half `?folder=` bought.
      openFile: (file: FileEntry) =>
        navigate(objectPath(file.id, { in: "f", id: folder })),
      fileHref: (file: FileEntry) =>
        objectPath(file.id, { in: "f", id: folder }),
    }),
    [folder, navigate, rootId, setFolderParam, sort],
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
 * ## The chip row is where the folder tabs went
 *
 * A character's root children each used to get a tab of their own, beside
 * Profile and References. That made a *listing* into navigation: the strip grew
 * and shrank as folders were created and deleted, every one of those tabs showed
 * a folder the browser one tab over already held, and at 390px the seven of them
 * wrapped into three rows of underline. They are shortcuts now — one scrolling
 * row of a fixed shape, with the browser still the only place a folder opens.
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
  return (
    <div className="flex w-full flex-col gap-4">
      <FolderShortcuts rootId={rootId} nav={nav} />
      <FolderBrowser nav={nav} boundary={rootId} boundaryLabel={label} />
    </div>
  );
}

/**
 * The root's immediate children, as jump targets.
 *
 * Fetched here rather than handed down because both callers want it and only one
 * of them ever had the listing to hand. It is the same `GET /api/tree` the
 * browser itself makes for the root, and it renders nothing at all when the root
 * has no subfolders — a character whose starting folders were deleted gets no
 * empty rail.
 *
 * Scrolls rather than wraps — see `ChipRow`, which the reference tag filter uses
 * too, so the two rows cannot drift apart.
 */
function FolderShortcuts({ rootId, nav }: { rootId: string; nav: BrowserNav }) {
  const load = useCallback(() => getFolder({ node: rootId }, "name"), [rootId]);
  const { data } = useResource(["folder-shortcuts", rootId], load);

  const folders = data?.folders ?? [];
  if (folders.length === 0) return null;

  const here = nav.folder;

  return (
    <ChipRow role="group" aria-label="Folder shortcuts">
      <FolderChip
        label="Top"
        active={here === rootId}
        onClick={() => nav.goToFolder(rootId)}
      />
      {folders.map((folder) => (
        <FolderChip
          key={folder.id}
          label={folder.name}
          active={here === folder.id}
          onClick={() => nav.goToFolder(folder.id)}
        />
      ))}
    </ChipRow>
  );
}

function FolderChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "true" : undefined}
      className={`shrink-0 snap-start rounded-none border px-3 py-1 font-body text-sm transition-colors
                  focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                    active
                      ? "border-primary bg-primary text-primary-text"
                      : "border-line text-muted hover:bg-surface-alt hover:text-ink"
                  }`}
    >
      {label}
    </button>
  );
}
