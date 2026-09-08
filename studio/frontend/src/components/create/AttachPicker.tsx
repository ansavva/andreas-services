import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Breadcrumbs,
  Button,
  Chip,
  IconButton,
  Text,
  Toggle,
  ToggleGroup,
} from "@ansavva/design-system";

import { getFolder } from "../../apis/studio";
import type { AttachRef, AttachRole } from "../../context/CreateBarContext";
import type { Crumb, FileEntry, FolderEntry } from "../../types";
import { MEDIA_GRID } from "../../utils/grid";
import type { FolderId } from "../../utils/location";
import { TagFilter } from "../browse/TagFilter";
import { EmptyState } from "../common/EmptyState";
import { ArrowUpIcon, CheckIcon, CloseIcon, FolderIcon } from "../common/icons";
import { LoadError } from "../common/LoadError";
import { SectionLoading } from "../common/SectionLoading";
import { MediaThumb } from "../media/MediaThumb";
import { ROLE_WORDS } from "./roles";

const VIEW_FOLDERS = "folders";
const VIEW_MEDIA = "media";
type View = typeof VIEW_FOLDERS | typeof VIEW_MEDIA;

/**
 * The picker: a second sheet above the create sheet while a tile is
 * highlighted, holding the library's file navigation — the same walk the
 * Files page offers, Folders and Media views included — so any picture in
 * the library can be a reference, a start frame or an end frame.
 *
 * **Pressing a picture attaches it.** There is no chosen-list and no Add
 * button: the tile in the sheet below IS the list, and a one-image role
 * replaces what it held. The picture stays marked here so the same one is
 * not sent twice.
 *
 * **Opens on the project's own folder, one press from anywhere.** Folders
 * is a readdir; Media is every picture under the current folder, which is
 * what the Files page means by it; a tag narrows either to the whole branch
 * — `default` from the library root is every character's identity images,
 * which is the trip "open the character, open reference, open face" used to
 * be. The `Project` and `Library` chips are the two places worth a jump.
 *
 * Images only, whichever view: every role a tile stands for is a picture,
 * and a clip cannot be one.
 */
export function AttachPicker({
  role,
  projectRoot,
  attached,
  onAttach,
  onClose,
}: {
  role: AttachRole;
  /** The project's root folder — where the picker opens. Null before it is known. */
  projectRoot: FolderId;
  /** Node ids already on the sheet, in any role. */
  attached: ReadonlySet<string>;
  onAttach: (ref: AttachRef) => void;
  onClose: () => void;
}) {
  const [folderId, setFolderId] = useState<FolderId>(projectRoot);
  const [view, setView] = useState<View>(VIEW_FOLDERS);
  const [tags, setTags] = useState<string[]>([]);
  const [folders, setFolders] = useState<FolderEntry[]>([]);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [crumbs, setCrumbs] = useState<Crumb[]>([]);
  const [deep, setDeep] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  // Stable, so the listing effect does not re-run on every render for a
  // fresh-but-equal array.
  const asked = tags.join(",");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    // By name: "newest first" answers a question nobody asks while looking for
    // a particular picture. `kind` is what makes Media a search of the branch
    // rather than a readdir — see `getFolder`.
    getFolder(folderId === null ? {} : { node: folderId }, "name", {
      tag: asked ? asked.split(",") : [],
      kind: view === VIEW_MEDIA ? ["image"] : [],
    })
      .then((result) => {
        if (cancelled) return;
        const searched = result.depth === "all";
        // Folders are the way to pictures at one level; in a result gathered
        // from the whole branch they are on the way to nothing.
        setFolders(searched ? [] : result.folders);
        setFiles(result.files.filter((file) => file.kind === "image"));
        setCrumbs(result.breadcrumbs);
        setDeep(searched);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [folderId, asked, view, attempt]);

  const parent = crumbs.at(-2)?.id;
  const words = ROLE_WORDS[role];
  const attach = useCallback(
    (file: FileEntry) =>
      onAttach({ node: file.id, url: file.url, name: file.name, kind: "object" }),
    [onAttach],
  );
  const empty = useMemo(() => folders.length === 0 && files.length === 0, [folders, files]);

  return (
    <div
      className="flex max-h-[60vh] flex-col gap-2 rounded-lg bg-sheet p-3 shadow-[0_12px_48px_rgba(0,0,0,0.55)]
                 ring-1 ring-line backdrop-blur-xl"
      data-attach-picker=""
      role="region"
      aria-label={words.choose}
    >
      <div className="flex items-center gap-2">
        <Text as="span" variant="body" weight="medium" className="min-w-0 flex-1 truncate">
          {words.choose}
        </Text>
        <ToggleGroup.Root
          aria-label="View"
          value={[view]}
          onValueChange={(next: string[]) => {
            const chosen = next[0];
            if (chosen === VIEW_FOLDERS || chosen === VIEW_MEDIA) setView(chosen);
          }}
          size="sm"
          className="gap-0.5 rounded-sm bg-fill p-0.5"
        >
          <Toggle value={VIEW_FOLDERS} className={pillClass(view === VIEW_FOLDERS)}>
            Folders
          </Toggle>
          <Toggle value={VIEW_MEDIA} className={pillClass(view === VIEW_MEDIA)}>
            Media
          </Toggle>
        </ToggleGroup.Root>
        <IconButton size="sm" label="Close the picker" onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Chip
          size="sm"
          pressed={folderId === projectRoot}
          disabled={projectRoot === null}
          onClick={() => setFolderId(projectRoot)}
        >
          Project
        </Chip>
        <Chip size="sm" pressed={folderId === null} onClick={() => setFolderId(null)}>
          Library
        </Chip>
        <Breadcrumbs.Root>
          {crumbs.map((crumb, index, all) => (
            <Breadcrumbs.Item
              key={crumb.id}
              current={index === all.length - 1}
              href="#"
              onClick={(event: React.MouseEvent) => {
                event.preventDefault();
                setFolderId(crumb.id);
              }}
            >
              {crumb.name}
            </Breadcrumbs.Item>
          ))}
        </Breadcrumbs.Root>
      </div>

      <TagFilter value={tags} onChange={setTags} searching={deep} />

      <div className="min-h-32 flex-1 overflow-y-auto rounded-md bg-fill-faint">
        {error ? (
          <LoadError
            what="the folder"
            message={error}
            onRetry={() => setAttempt((n) => n + 1)}
          />
        ) : loading ? (
          <SectionLoading label="Loading folder" />
        ) : (
          <div className="flex flex-col">
            {parent !== undefined && !deep && (
              <FolderRow icon={<ArrowUpIcon className={ROW_GLYPH} />} name="Up one folder" onClick={() => setFolderId(parent)} />
            )}
            {folders.map((folder) => (
              <FolderRow
                key={folder.id}
                icon={<FolderIcon className={ROW_GLYPH} />}
                name={folder.name}
                onClick={() => setFolderId(folder.id)}
              />
            ))}
            {files.length > 0 && (
              <div className={`${MEDIA_GRID} p-2`}>
                {files.map((file) => {
                  const on = attached.has(file.id);
                  return (
                    <Button
                      key={file.id}
                      intent="secondary"
                      size="sm"
                      aria-pressed={on}
                      aria-label={`Attach ${file.name}`}
                      title={file.name}
                      className={`relative h-auto flex-col items-stretch gap-1 rounded-md bg-transparent p-1 text-left
                                  hover:bg-fill active:bg-fill-active ${on ? "ring-2 ring-primary" : ""}`}
                      onClick={() => attach(file)}
                    >
                      <MediaThumb
                        nodeId={file.id}
                        url={file.url}
                        name={file.name}
                        aspect="portrait"
                        dimmed={on}
                        className="w-full"
                      />
                      <Text variant="caption" tone="muted" truncate>
                        {file.name}
                      </Text>
                      {on && (
                        <span className="absolute right-2 top-2 flex size-6 items-center justify-center rounded-pill bg-primary text-primary-text">
                          <CheckIcon className="size-3.5 fill-none stroke-current stroke-[2.5]" />
                        </span>
                      )}
                    </Button>
                  );
                })}
              </div>
            )}
            {empty && !deep && <EmptyState title="No pictures here yet." className="p-3" />}
            {empty && deep && (
              <EmptyState
                title={
                  tags.length > 0
                    ? `Nothing under this folder is tagged ${tags.join(" + ")}.`
                    : "Nothing under this folder is a picture."
                }
                className="p-3"
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const ROW_GLYPH = "size-5 shrink-0 fill-none stroke-muted stroke-[1.5]";

/** A folder, or the way up, as a row — the picker's twin of the Files page's. */
function FolderRow({
  icon,
  name,
  onClick,
}: {
  icon: React.ReactNode;
  name: string;
  onClick: () => void;
}) {
  return (
    <Button
      intent="secondary"
      size="md"
      className="h-10 w-full justify-start gap-2 rounded-none bg-transparent px-3 font-normal hover:bg-fill"
      onClick={onClick}
    >
      {icon}
      <span className="truncate">{name}</span>
    </Button>
  );
}

/** One half of the Folders / Media switch — the create sheet's pills. */
function pillClass(on: boolean): string {
  return `h-7 rounded-xs px-2.5 text-sm ${
    on
      ? "bg-fill-active text-ink hover:bg-fill-active active:bg-fill-active"
      : "text-muted hover:bg-fill hover:text-ink"
  }`;
}
