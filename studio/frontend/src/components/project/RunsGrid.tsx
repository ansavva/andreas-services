import { useCallback } from "react";

import { getFolder } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { EmptyState } from "../common/EmptyState";
import { SectionLoading } from "../common/SectionLoading";
import { LoadError } from "../common/LoadError";
import { FolderBrowser } from "../browse/FolderBrowser";
import { useLocalBrowserNav } from "../browse/FolderTab";

/**
 * The name a run's outputs are filed under, and the backend's own convention.
 *
 * `services/layout.py` resolves `runs` **by name at write time and creates it if
 * it is absent**, so looking it up the same way is not a second convention — it
 * is the same one, read. If somebody renames the folder, the next run makes a
 * new `runs` beside it and every existing run stays reachable by id; this grid
 * follows whichever one the next run would write into, which is the honest
 * answer rather than a guess at which of the two was meant.
 */
const RUNS_FOLDER = "runs";

/**
 * Every output every run in this project produced, as one grid.
 *
 * **This is the file browser, not a second implementation of it**, scoped to the
 * project's `runs/` folder and opened in Media view. That is the whole design:
 * a run's outputs are ordinary nodes under that folder, so "show me everything
 * this project has made" is a question the listing already answers —
 * `kind=image,video`, which `getFolder` sends with `depth=all`. A grid of its
 * own would be a second thing to keep looking like the first.
 *
 * What it buys over the list beside it is that the unit on screen is the
 * *picture*. `RunsTable`'s unit is the run — status, model, cost, the plan that
 * produced it — none of which a frame can show, which is why that view stays and
 * this does not replace it.
 *
 * ## Why it does not label each tile with its run
 *
 * Because that is not free, and a wrong label is worse than none. A listing
 * deliberately does not resolve `owner` for a deep row (`services/browse.py`:
 * two rows a hundred nodes apart share nothing, so it would be a batched read
 * per thumbnail), and the runs listing projects only the *first* output onto its
 * row as `thumb`. Provenance is one click away instead: opening a tile is the
 * viewer, which resolves the owning run for the one node it is drawing.
 *
 * ## The empty case is ordinary
 *
 * A project with no runs has no `runs/` folder, because the folder is made by
 * the first run rather than by the project. So its absence is "nothing has been
 * made yet", not an error, and it reads as that.
 */
export function RunsGrid({ projectId, rootId }: { projectId: string; rootId: string }) {
  // The project root's children, which is the same request `FolderShortcuts`
  // makes one level down — one small listing, by name so the lookup is stable.
  const load = useCallback(() => getFolder({ node: rootId }, "name"), [rootId]);
  const { data, loading, error, reload } = useResource(
    ["project-root", projectId],
    load,
  );

  if (loading) return <SectionLoading label="Loading outputs" />;
  if (error) return <LoadError what="outputs" message={error} onRetry={reload} />;

  const runs = data?.folders.find((folder) => folder.name === RUNS_FOLDER);
  if (!runs) return <EmptyState title="No outputs yet." hint="Outputs appear here once a run succeeds." />;

  return <RunsBrowser rootId={runs.id} />;
}

/**
 * The browser itself, split out so the hook driving it is called at the top of
 * *something* — the same reason `FolderTab` is its own component. The folder id
 * is only known once the listing above has landed, and a hook cannot sit after
 * an early return.
 *
 * **No folder shortcut chips, which `FolderTab` would draw.** The children of
 * `runs/` are one folder per run, named by the run id, so the chip row would be
 * a scrolling rail of `run-<uuid>` — navigation built out of strings nobody
 * reads. The runs themselves are the tab's other view, one press away, and it
 * names them by model and by when.
 */
function RunsBrowser({ rootId }: { rootId: string }) {
  const nav = useLocalBrowserNav(rootId, "runsFolder");
  return (
    <FolderBrowser
      nav={nav}
      boundary={rootId}
      boundaryLabel="Runs"
      defaultView="media"
      viewParam="runsView"
    />
  );
}
