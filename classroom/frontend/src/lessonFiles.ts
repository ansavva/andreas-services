import JSZip from "jszip";

/**
 * One file on its way to S3, with the relative path it must land on.
 *
 * All three ways a teacher can hand over a lesson — a single `.html`, a `.zip`
 * from her authoring tool, or a folder she picks — are reduced to a list of
 * these before anything is uploaded. Everything downstream (signing, PUTting,
 * publishing) then has exactly one shape to deal with.
 */
export interface LessonFile {
  path: string;
  blob: Blob;
}

export const INDEX_FILE = "index.html";

/**
 * Strip a wrapper directory that contains everything.
 *
 * Zips and folder pickers almost always nest their contents one level down —
 * `Warm Up Fractions/index.html`, not `index.html`. Left alone, the lesson's
 * index would sit at a path that `/lesson/<id>/` never resolves to, so the
 * lesson would 404 with every file present and correct. Dropping the shared
 * root is what makes "just upload what my tool gave me" work.
 *
 * Only ever ONE level, and only when it is genuinely shared by every entry —
 * a lesson that legitimately puts everything under `assets/` keeps it, because
 * `index.html` would not be inside it.
 */
function stripCommonRoot(files: LessonFile[]): LessonFile[] {
  if (files.length === 0) return files;

  const roots = new Set(files.map((f) => f.path.split("/")[0] ?? ""));
  if (roots.size !== 1) return files;

  const [root] = [...roots];
  // Every path is `root/...`, and nothing sits at the top level.
  if (!root || files.some((f) => !f.path.startsWith(`${root}/`))) return files;

  const stripped = files.map((f) => ({ ...f, path: f.path.slice(root.length + 1) }));
  // Only worth it if it actually surfaces the index.
  return stripped.some((f) => f.path === INDEX_FILE) ? stripped : files;
}

/** Files a zip or a folder carries that are not the teacher's content. */
function isNoise(path: string): boolean {
  const name = path.split("/").pop() ?? "";
  return (
    path.startsWith("__MACOSX/") || // macOS resource forks, in every zip made on a Mac
    name === ".DS_Store" ||
    name === "Thumbs.db" ||
    name.startsWith("._") ||
    path.split("/").some((segment) => segment === ".git")
  );
}

/** A single `.html` file becomes the lesson's index, whatever she called it. */
async function fromSingleHtml(file: File): Promise<LessonFile[]> {
  return [{ path: INDEX_FILE, blob: file }];
}

async function fromZip(file: File): Promise<LessonFile[]> {
  const zip = await JSZip.loadAsync(file);
  const out: LessonFile[] = [];
  for (const entry of Object.values(zip.files)) {
    if (entry.dir || isNoise(entry.name)) continue;
    out.push({ path: entry.name, blob: await entry.async("blob") });
  }
  return out;
}

function fromFileList(files: File[]): LessonFile[] {
  return files
    // `webkitRelativePath` is what a directory picker fills in; a plain
    // multi-select leaves it empty, in which case the name is the path.
    .map((file) => ({
      path: (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name,
      blob: file,
    }))
    .filter((f) => !isNoise(f.path));
}

export class LessonFilesError extends Error {}

/**
 * Turn whatever she dropped in into the list of files to upload.
 *
 * Throws `LessonFilesError` with something a teacher can act on, rather than
 * letting an empty or index-less upload reach the API and come back as a
 * validation error phrased for a developer.
 */
export async function collectLessonFiles(selected: File[]): Promise<LessonFile[]> {
  if (selected.length === 0) throw new LessonFilesError("No files were chosen.");

  let files: LessonFile[];
  const [only] = selected;

  if (selected.length === 1 && only && /\.zip$/i.test(only.name)) {
    files = await fromZip(only);
  } else if (selected.length === 1 && only && /\.html?$/i.test(only.name)) {
    files = await fromSingleHtml(only);
  } else {
    files = fromFileList(selected);
  }

  files = stripCommonRoot(files.filter((f) => f.blob.size > 0 || f.path === INDEX_FILE));

  if (files.length === 0) {
    throw new LessonFilesError("That upload had no files in it.");
  }
  if (!files.some((f) => f.path === INDEX_FILE)) {
    const html = files.filter((f) => /\.html?$/i.test(f.path));
    // The commonest real mistake: an export named after the document rather
    // than `index.html`. Say which file to rename instead of just refusing.
    if (html.length === 1 && html[0]) {
      throw new LessonFilesError(
        `This needs a file called ${INDEX_FILE} at the top level. Rename “${html[0].path}” to ${INDEX_FILE} and try again.`,
      );
    }
    throw new LessonFilesError(
      `This needs a file called ${INDEX_FILE} at the top level — that is the page students open.`,
    );
  }
  return files;
}
