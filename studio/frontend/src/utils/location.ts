/**
 * The URL names a node, by id.
 *
 * `/f/<node_id>` is a folder and `/o/<node_id>` is one file, open. Nothing about
 * where the node sits appears in the address — that is the point of #313. Two
 * things follow, and both were the reasons the URL used to be the S3 key:
 *
 * * **A share link survives a rename and a move.** Renaming a clip used to
 *   invalidate every link to it, because the link *was* its key. A node id is
 *   the one thing about a node that never changes, so the link outlives both.
 * * **There is nothing left to encode.** A node id is a v4 UUID, so the
 *   per-segment encoding this file used to carry — there to keep the spaces and
 *   `#` in real filenames from eating the separators — has nothing to protect
 *   any more. `legacyPath` still decodes, because the paths *it* reads are the
 *   old key-shaped links and those still contain both.
 *
 * **`/f/` and `/o/` are reserved.** An old share link is matched by exclusion —
 * anything that is neither is handed to the resolver — so a library holding a
 * top-level folder named `f` or `o` would shadow one of these. The root holds
 * `projects/` and `characters/`, and the resolver is a bridge that comes out
 * once no old link is in circulation, so this is stated rather than defended.
 *
 * **CloudFront still has to agree, and still needs no change.** Its
 * viewer-request function routes by *location* — `/assets/…` and `/index.html`
 * pass through, everything else rewrites to `index.html` — rather than by "does
 * this look like a file". The new ids are extensionless and the old links end in
 * `.mp4`; a location rule serves both, and an extension rule would break the
 * second. See `infra/modules/hosting/main.tf`.
 */

/**
 * The library root, and the one folder addressed by something other than an id.
 *
 * Its id is not knowable before the first request — `/api/libraries` returns the
 * library, not its root node — so an app that insisted on `/f/<id>` everywhere
 * would have to resolve before it could draw anything. `GET /api/tree` with
 * neither `?node=` nor `?prefix=` is already the root, so `/` costs no lookup.
 * It is also where sign-out lands.
 */
export const ROOT_PATH = "/";

/** A folder node id, or `null` for the library root. */
export type FolderId = string | null;

export type Target = { kind: "folder"; id: FolderId } | { kind: "object"; id: string };

/** The in-app path for a folder. */
export function folderPath(id: FolderId): string {
  return id === null ? ROOT_PATH : `/f/${id}`;
}

/** The in-app path for one open file — this is the share link. */
export function objectPath(id: string): string {
  return `/o/${id}`;
}

/**
 * Read a pathname back into what it points at.
 *
 * Anything unrecognised resolves to the root rather than erroring, which is the
 * same bargain the key-shaped version made: a stale bookmark should land
 * somewhere usable instead of on a crash. In practice the router has already
 * sent the old shapes to the resolver, so what reaches here unrecognised is a
 * hand-edited URL.
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

/**
 * An old key-shaped URL as the name path `GET /api/resolve` takes.
 *
 * Every segment is decoded individually — encoding was applied that way, and the
 * separators would be eaten by decoding the whole string at once. The trailing
 * slash that used to mean "folder" is dropped rather than read: `/api/resolve`
 * returns the node's `kind`, so the distinction the slash carried is now
 * answered by the thing being resolved instead of guessed from its address.
 */
export function legacyPath(pathname: string): string {
  return pathname
    .split("/")
    .filter(Boolean)
    .map((segment) => {
      try {
        return decodeURIComponent(segment);
      } catch {
        // A hand-edited URL can carry a stray `%`. Better to resolve a name
        // that does not exist — which is a 404 the resolver reports — than to
        // throw on the way to rendering.
        return segment;
      }
    })
    .join("/");
}
