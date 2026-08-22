import { confirmUpload, createNode, deleteNode, getUploadUrl } from "./studio";
import type { NodeRecord, UploadGrant } from "../types";

/**
 * One file into the folder you are looking at, in four steps.
 *
 * ## Why four, and why one of them is not `fetch`
 *
 * `POST /api/nodes` mints a placeholder, which is what names the key; `POST
 * /api/nodes/<id>/upload-url` signs a PUT for exactly that key, that length and
 * that type; the bytes go **straight to S3**; `POST
 * /api/nodes/<id>/confirm-upload` writes the size the bucket reports onto the
 * row. The bytes never transit the Lambda, which is the whole reason this is
 * four calls rather than one — a 6 MB request limit against a video is not a
 * limit you tune around.
 *
 * The PUT is **`XMLHttpRequest`, and nothing else in this app is.** `fetch`
 * cannot report upload progress: its `Response` is the download, and there is no
 * event for how much of a request body has gone out. Streaming a request body
 * would let you count it yourself, but it needs `duplex: "half"` over HTTP/2 and
 * is not a thing Safari does — which is the browser this feature exists for.
 * XHR's `upload.onprogress` is thirteen years old and works everywhere. A
 * 300 MB clip over a phone connection with no bar is indistinguishable from a
 * frozen tab, so the bar is not decoration and neither is the choice.
 *
 * ## What a failure leaves behind
 *
 * The row is minted before its bytes, so every failure after step 1 leaves a
 * **placeholder** — a row naming `blobs/<id>` with nothing behind it. That is not
 * invisible: `browse._file_entry` presigns any row carrying a `blob_key`, so the
 * grid draws it as a tile that will not load. **`studio catalog gc` does not
 * collect it** — that command deletes blobs no row names, which is the opposite
 * direction — so this deletes the node itself rather than leaving one behind.
 *
 * A failure at the *confirm* is the one exception and is left alone: the bytes
 * are in the bucket and the row names them, so the file works and only its size
 * reads 0. Destroying a completed upload to tidy a number is the wrong trade,
 * and re-running the confirm is what fixes it.
 *
 * If the cleanup itself fails — the connection that killed the PUT is usually
 * still dead — the broken tile stays. Deleting it is one press in the row's `⋯`
 * menu, and that is the honest fallback rather than a retry loop.
 */

/**
 * Headers a browser refuses to let script set, so we do not pretend to.
 *
 * `Content-Length` is a forbidden header name: `setRequestHeader` for it is a
 * silent no-op, per the Fetch spec's forbidden-header list, and the browser
 * computes the value from the body instead. The signature still validates
 * because the value the browser computes is `file.size`, which is the number
 * `upload-url` was asked to sign — so this works by *agreement*, not because the
 * header was sent. Skipping it explicitly beats calling a no-op that a reader
 * would take for a working line.
 */
const BROWSER_OWNED_HEADERS = new Set(["content-length"]);

/**
 * Formats iOS hands over that this app cannot then display.
 *
 * An iPhone photographs to HEIC by default, and Safari will happily upload one.
 * Nothing else decodes it: `keys.IMAGE_EXTENSIONS` does not list `.heic`, so the
 * catalog classifies it as `other` and it lands as a file row rather than a
 * tile — and even opened directly, every browser but Safari shows nothing.
 *
 * **Refused before the node is created**, with a message naming the fix, rather
 * than accepted and left to be discovered. The alternative — accept it and let
 * the content type ride — is an upload that appears to succeed and produces a
 * file the library cannot show, which is the one outcome worth ruling out. It is
 * refused on extension *and* type because Safari sometimes hands over an empty
 * `type` and sometimes `image/heic`.
 */
const UNDISPLAYABLE = {
  extensions: [".heic", ".heif"],
  types: ["image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence"],
};

/** Why this file cannot be uploaded, or `null` if it can. */
export function rejectionFor(file: File): string | null {
  const name = file.name.toLowerCase();
  const type = file.type.toLowerCase();
  if (
    UNDISPLAYABLE.extensions.some((ext) => name.endsWith(ext)) ||
    UNDISPLAYABLE.types.includes(type)
  ) {
    return (
      `${file.name} is HEIC, which this library cannot display. ` +
      "On iPhone: Settings › Camera › Formats › Most Compatible, then take it again — " +
      "or share it as a JPEG."
    );
  }
  return null;
}

/**
 * What S3 falls back to when a file has no type, which is often on Android.
 *
 * The API requires a non-empty `content_type` — it is a signed header, so there
 * is nothing to sign without one. `application/octet-stream` is what S3 itself
 * would have stored, and the app classifies by *extension* anyway
 * (`keys.kind`), so a generic type costs a tile nothing.
 */
export function contentTypeOf(file: File): string {
  return file.type || "application/octet-stream";
}

export interface UploadProgress {
  /** Bytes sent so far, and the total. `loaded === total` is not "confirmed". */
  loaded: number;
  total: number;
}

/**
 * PUT one file to a signed URL, reporting progress.
 *
 * Rejects on a non-2xx status and on a transport failure, and both matter: S3
 * answers a failed signature with a 403 carrying an XML body, so a status check
 * is the only thing standing between "refused" and "uploaded".
 */
export function putSigned(
  grant: UploadGrant,
  file: File,
  { onProgress, signal }: { onProgress?: (p: UploadProgress) => void; signal?: AbortSignal } = {},
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", grant.url);

    for (const [header, value] of Object.entries(grant.headers)) {
      if (BROWSER_OWNED_HEADERS.has(header.toLowerCase())) continue;
      xhr.setRequestHeader(header, value);
    }

    if (onProgress) {
      xhr.upload.onprogress = (event) => {
        // `lengthComputable` is false for a body the browser has not sized yet;
        // reporting 0/0 then would make the bar jump backwards.
        if (event.lengthComputable) onProgress({ loaded: event.loaded, total: event.total });
      };
    }

    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new Error(`Upload refused by storage (${xhr.status})`));
    xhr.onerror = () => reject(new Error("Upload failed — the connection dropped"));
    xhr.onabort = () => reject(new Error("Upload cancelled"));
    xhr.ontimeout = () => reject(new Error("Upload timed out"));

    signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(file);
  });
}

/**
 * The whole sequence for one file. Resolves with the node as the catalog holds
 * it — including the name it actually took, which numbering may have changed.
 */
export async function uploadFile(
  parentId: string,
  file: File,
  { onProgress, signal }: { onProgress?: (p: UploadProgress) => void; signal?: AbortSignal } = {},
): Promise<NodeRecord> {
  const refusal = rejectionFor(file);
  if (refusal) throw new Error(refusal);

  // `on_conflict: "number"` rather than a name this client made up. An uploaded
  // file keeps the name it arrived with, and the catalog decides what to do when
  // that name is taken — see `catalog.create_numbered`.
  const node = await createNode(parentId, file.name, "file", { onConflict: "number" });

  let grant: UploadGrant;
  try {
    grant = await getUploadUrl(node.id, file.size, contentTypeOf(file));
    await putSigned(grant, file, { onProgress, signal });
  } catch (err) {
    // Best effort, and deliberately not awaited into the failure path's message:
    // what the caller needs to hear is why the upload failed, not why the tidy-up
    // of it did.
    void deleteNode(node.id).catch(() => undefined);
    throw err;
  }

  return confirmUpload(node.id);
}
