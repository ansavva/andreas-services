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

/** The in-app path for one open file — this is the share link. */
export function objectPath(id: string): string {
  return `/o/${id}`;
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
