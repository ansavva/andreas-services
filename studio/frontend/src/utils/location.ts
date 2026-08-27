/**
 * Every URL in this app names an entity or a node, by id.
 *
 * | URL | What it is |
 * |---|---|
 * | `/` | Home — characters, projects, and what was made most recently |
 * | `/c/<char_id>` · `/p/<proj_id>` | a character, a project |
 * | `/p/<proj_id>/r/<run_id>` | one run, inside the project that owns it |
 * | `/s/<scene_id>` · `/m/<movie_id>` | a scene, a movie |
 * | `/f/<node_id>` · `/o/<node_id>` | the folder browser, one open file |
 *
 * **Ids everywhere, so every link survives every rename.** That was already true
 * of `/f/` and `/o/` (#313) and it is now true of the entities too, which is the
 * whole reason a character is a row with a UUID rather than a folder called by
 * its slug: renaming one used to invalidate every address anybody held.
 *
 * **The legacy resolver is gone.** Studio used to hand out the S3 key as the URL
 * — `/projects/<project>/runs/…/output/clip.mp4` — and `LegacyRedirect` matched
 * those by exclusion and asked the API what they named. It was always a bridge
 * with a lifetime, and the entity rework is where it ends: no back-compat is
 * carried, so an unrecognised path lands on home rather than being resolved.
 * That also frees the top-level namespace the bridge was occupying, which is how
 * `/c/`, `/p/`, `/s/` and `/m/` became available at all.
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
 * away at `/f`, but what studio opens on is characters and projects.
 */
export const HOME_PATH = "/";

/**
 * The two entity indexes, which the header links to.
 *
 * Home still lists both, and these are not a demotion of it: a list you scroll
 * to reach is not navigation, and "where are my characters" was previously
 * answerable only by going home and looking down the page. They render the same
 * sections home does, unabridged.
 */
export const CHARACTERS_PATH = "/characters";
export const PROJECTS_PATH = "/projects";

/** A folder node id, or `null` for the library root. */
export type FolderId = string | null;

export type Target = { kind: "folder"; id: FolderId } | { kind: "object"; id: string };

/**
 * The in-app path for a folder.
 *
 * The library root is `/f` with no id, and that is not an inconsistency worth
 * fixing: its id is not knowable before the first request — `/api/libraries`
 * returns the library, not its root node — so an app that insisted on
 * `/f/<id>` would have to resolve before it could draw anything, and
 * `GET /api/tree` with no address is already that folder.
 */
export function folderPath(id: FolderId): string {
  return id === null ? "/f" : `/f/${id}`;
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
  | { in: "run" | "scene" | "refs"; id: string };

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

/**
 * The viewer opened on a *feed* rather than on a file — "play this from the
 * start".
 *
 * `/o` with no id, which the route table allows deliberately. The alternative
 * was for "Play reel" to fetch a page, read the first item's id and navigate to
 * that, which is a request made solely to build a URL that the viewer is about
 * to make again. The viewer opens on the first pane and rewrites the address to
 * it, so the id appears a moment later without anybody waiting for it.
 */
export function feedPath(from: ViewerSource): string {
  return `/o?in=${encodeURIComponent(sourceParam(from))}`;
}

export function characterPath(id: string): string {
  return `/c/${id}`;
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
