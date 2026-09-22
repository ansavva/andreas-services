/**
 * Every URL in this app names an entity or a node, by id.
 *
 * | URL | What it is |
 * |---|---|
 * | `/` | Home — favorites, characters and projects |
 * | `/favorites` | every image and video this person picked out |
 * | `/c/<char_id>` · `/p/<proj_id>` | a character, a project |
 * | `/p/<proj_id>/r/<run_id>` | one run, inside the project that owns it |
 * | `/s/<scene_id>` · `/m/<movie_id>` | a scene, a movie |
 * | `/f/<node_id>` · `/o/<node_id>` | the folder browser, one open file |
 *
 * **Ids everywhere, so every link survives every rename.** That is the whole
 * reason a character is a row with a UUID rather than a folder called by its
 * name: renaming a folder would invalidate every address anybody held.
 *
 * An unrecognised path lands on home; nothing here resolves a path by asking
 * the API.
 *
 * **CloudFront still needs no change.** Its viewer-request function routes by
 * *location* — `/assets/…` and `/index.html` pass through, everything else
 * rewrites to `index.html` — rather than by "does this look like a file". See
 * `infra/modules/hosting/main.tf`.
 */

/**
 * Home, and where sign-out lands.
 *
 * It is the entity index rather than the library's file listing, which is the
 * one visible reversal in the new shell: the file browser is still one click
 * away at `/f`, but what studio opens on is what somebody picked out, and then
 * the characters and projects it came from.
 */
export const HOME_PATH = "/";

/**
 * The two entity indexes, which the header links to.
 *
 * Home still lists both, and these are not a demotion of it: a list you scroll
 * to reach is not navigation, and "where are my characters" deserves a better
 * answer than going home and looking down the page. They render the same
 * sections home does, unabridged.
 */
export const CHARACTERS_PATH = "/characters";
export const LOCATIONS_PATH = "/locations";
export const PROJECTS_PATH = "/projects";
/**
 * The favorites screen — every image and video this person picked out.
 *
 * A real address rather than only a section of home, for the reason the two
 * indexes above are: home leads with it, and a list you scroll to reach is not
 * navigation. Home shows the first row and links here for the rest.
 *
 * **No id in it, and there could not be one.** A favorite is a fact about the
 * caller, so the collection is whoever is signed in — there is nothing to name.
 */
export const FAVORITES_PATH = "/favorites";
/**
 * The reference spec belongs to the LIBRARY, not to a character: one set of
 * angles describes every character in it. So it is a section, beside the two
 * listings, rather than a tab on a character page.
 */
export const TEMPLATES_PATH = "/templates";

/** A folder node id, or `null` for the library root. */
export type FolderId = string | null;

type Target = { kind: "folder"; id: FolderId } | { kind: "object"; id: string };

/**
 * The in-app path for a folder.
 *
 * The library root is `/f` with no id, and that is not an inconsistency worth
 * fixing: its id is not knowable before the first request — `/api/libraries`
 * returns the library, not its root node — so an app that insisted on
 * `/f/<id>` would have to resolve before it could draw anything, and
 * `GET /api/nodes` with no `under` is already that folder.
 */
export function folderPath(id: FolderId): string {
  return id === null ? "/f" : `/f/${id}`;
}

/**
 * The listing's state, as the query string a share link carries.
 *
 * `/f/<id>` alone lands on the folder; this is the rest of what somebody was
 * looking at — the Media view, a sort, a tag filter, a typed name. Written in
 * the names `BrowsePage` and `FolderBrowser` read on `/f` (`view`, `sort`,
 * `tags`, `q`), whatever names the browser that built it was using: a Files
 * tab sorts under `fsort` and a project's Runs grid views under its own key,
 * and a link copied from either has to open on `/f`, where those names mean
 * nothing.
 *
 * Every default is absence, the same rule `useSearchParamState` writes with,
 * so a folder at rest links as `/f/<id>` and nothing more.
 */
export function folderLink(
  id: FolderId,
  state: { view?: string; sort?: string; tags?: string[]; q?: string },
  defaults: { view: string; sort: string },
): string {
  const params = new URLSearchParams();
  if (state.view && state.view !== defaults.view) params.set("view", state.view);
  if (state.sort && state.sort !== defaults.sort) params.set("sort", state.sort);
  if (state.tags && state.tags.length > 0)
    params.set("tags", state.tags.map(encodeURIComponent).join(","));
  if (state.q) params.set("q", state.q);
  const query = params.toString();
  return query ? `${folderPath(id)}?${query}` : folderPath(id);
}

/**
 * An in-app path as the URL that goes on the clipboard.
 *
 * Every builder here returns a path, because a path is what `navigate` and an
 * `href` take; a link handed to another person has to carry the origin too,
 * and this is the one place it is added. `window.location.origin`, not a
 * configured value: the app knows where it is being served from, and a
 * constant would be one more thing for dev and prod to disagree on.
 */
export function absoluteUrl(path: string): string {
  return `${window.location.origin}${path}`;
}

/**
 * What the viewer is scrolling THROUGH, carried in the address.
 *
 * **A file opened from a run and the same file opened from a folder are not the
 * same screen**, and until now they were: `/o/<id>` meant "the folder browser,
 * with this file open over it", so opening a run's output teleported you into
 * the file tree and the run you were reading vanished. The neighbours are what
 * differ, so the neighbours are what the address names.
 *
 * Absent is a real state and the one a share link usually has: show the file
 * alone and say which entity it belongs to. It is not an error and does not
 * redirect.
 */
export type ViewerSource =
  | { in: "f" | "recursive"; id: FolderId }
  | { in: "run" | "scene" | "refs"; id: string }
  /**
   * The favorites grid. **The one source with no id at all**, because there is
   * nothing to name: the collection is whoever is signed in. It is spelled
   * `id: null` rather than dropped from the shape so every reader keeps one
   * field to switch on.
   */
  | { in: "fav"; id: null };

/** The `?in=` value: `f`, `f:<node>`, `run:<id>`, … */
export function sourceParam({ in: kind, id }: ViewerSource): string {
  return id === null ? kind : `${kind}:${id}`;
}

/** Read one back. Anything unrecognised is "no context", which is a legal state. */
export function sourceFromParam(value: string | null): ViewerSource | null {
  if (!value) return null;
  const [kind, id] = value.split(":", 2) as [string, string | undefined];

  // `id || null`, not `id ?? null`: `f:` with nothing after it is how an
  // encoder that interpolated a null folder spells the library root, and "" is
  // not a node anything can look up.
  if (kind === "fav") return { in: "fav", id: null };
  if (kind === "f" || kind === "recursive") return { in: kind, id: id || null };
  if (kind === "run" || kind === "scene" || kind === "refs") {
    return id ? { in: kind, id } : null;
  }
  return null;
}

/**
 * The in-app path for one open file — this is the share link.
 *
 * The id alone is the durable half: it survives every rename and every move, and
 * a link that has lost its `?in=` still opens the file. The context is a
 * convenience for whoever is *browsing*, so it is a query parameter rather than
 * a path segment — nothing about the file's identity depends on it.
 */
export function objectPath(id: string, from?: ViewerSource | null): string {
  return from ? `/o/${id}?in=${encodeURIComponent(sourceParam(from))}` : `/o/${id}`;
}

export function characterPath(id: string): string {
  return `/c/${id}`;
}

/** `/l/<id>` — a location, the way `/c/` is a character. */
export function locationPath(id: string): string {
  return `/l/${id}`;
}

export function projectPath(id: string): string {
  return `/p/${id}`;
}

/**
 * A run's path, which carries its project as well as its own id.
 *
 * The run id alone would be enough to fetch it — the envelope names its project
 * — but the URL is also a breadcrumb, and a person who lands on a run from a
 * pasted link should be one click from the project it belongs to without waiting
 * for a request to tell them there is one.
 */
export function runPath(projectId: string, runId: string): string {
  return `/p/${projectId}/r/${runId}`;
}

/**
 * A project's reel — everything in it, oldest first, one item per screen.
 *
 * Under the project's path, like a run: closing it is the project again.
 */
export function reelPath(projectId: string): string {
  return `/p/${projectId}/reel`;
}

export function scenePath(id: string): string {
  return `/s/${id}`;
}

export function moviePath(id: string): string {
  return `/m/${id}`;
}

/**
 * Read a pathname back into what the browser is showing.
 *
 * Only the two browser shapes, because only the browser reads its address this
 * way — the entity pages take their id from the router's own params. Anything
 * unrecognised resolves to the library root rather than erroring: a stale
 * bookmark should land somewhere usable instead of on a crash.
 */
export function targetFromPath(pathname: string): Target {
  const segments = pathname.split("/").filter(Boolean);
  const [scope, id] = segments;

  if (segments.length === 2 && id) {
    if (scope === "f") return { kind: "folder", id };
    if (scope === "o") return { kind: "object", id };
  }

  return { kind: "folder", id: null };
}
