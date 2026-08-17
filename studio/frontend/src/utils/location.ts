/**
 * The URL *is* the S3 path.
 *
 * `studio.andreas.services/media/fred/runs/2026-08-14_.../output/clip.mp4` opens
 * that clip; `studio.andreas.services/media/fred/runs/` opens that folder. The
 * trailing slash is the whole distinction, and it is the same one S3 makes —
 * which is why it is carried rather than normalised away.
 *
 * Two consequences worth knowing before changing anything here:
 *
 * * **A share link is a key, so it must survive a round trip.** Every segment is
 *   encoded and decoded individually: encoding the whole path would eat the
 *   separators, and not encoding at all would break on the spaces and `#` that
 *   real filenames in this bucket contain.
 * * **CloudFront has to agree.** A key ending in `.mp4` looks exactly like a
 *   static asset, so `modules/hosting`'s viewer-request function routes by
 *   location (`/assets/…`) rather than by extension. Change one and the other
 *   stops being true.
 */

export const ROOT_PREFIX = "media/";

export type Target =
  | { kind: "folder"; prefix: string }
  | { kind: "object"; key: string; prefix: string };

function encodeKey(key: string): string {
  return key
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

function decodeKey(path: string): string {
  return path
    .split("/")
    .map((segment) => {
      try {
        return decodeURIComponent(segment);
      } catch {
        // A hand-edited URL can contain a stray `%`. Better to look for a key
        // that does not exist than to throw on the way to rendering.
        return segment;
      }
    })
    .join("/");
}

/** The folder one key sits in — always ending in a slash. */
export function parentPrefix(key: string): string {
  const trimmed = key.replace(/\/+$/, "");
  const cut = trimmed.lastIndexOf("/");
  return cut < 0 ? ROOT_PREFIX : trimmed.slice(0, cut + 1);
}

export function basename(key: string): string {
  const trimmed = key.replace(/\/+$/, "");
  return trimmed.slice(trimmed.lastIndexOf("/") + 1);
}

/** The in-app path for a folder. Always ends in a slash. */
export function folderPath(prefix: string): string {
  return `/${encodeKey(prefix)}`;
}

/** The in-app path for one object — this is the share link. */
export function objectPath(key: string): string {
  return `/${encodeKey(key)}`;
}

/**
 * Read a pathname back into what it points at.
 *
 * Anything that does not sit under `media/` resolves to the root rather than
 * erroring: the API validates keys properly and will say so, and a stale
 * bookmark should land somewhere usable instead of on a crash.
 */
export function targetFromPath(pathname: string): Target {
  const raw = decodeKey(pathname.replace(/^\/+/, ""));

  if (!raw || !`${raw}/`.startsWith(ROOT_PREFIX)) {
    return { kind: "folder", prefix: ROOT_PREFIX };
  }

  if (raw.endsWith("/")) {
    return { kind: "folder", prefix: raw };
  }

  // `media` with no trailing slash is still the root folder, not an object
  // called `media`.
  if (`${raw}/` === ROOT_PREFIX) {
    return { kind: "folder", prefix: ROOT_PREFIX };
  }

  return { kind: "object", key: raw, prefix: parentPrefix(raw) };
}
