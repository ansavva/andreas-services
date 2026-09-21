import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  Breadcrumbs,
  Button,
  Chip,
  Drawer,
  Text,
  Toggle,
  ToggleGroup,
} from "@ansavva/design-system";

import {
  getAsset,
  getCharacters,
  getFolder,
  getLocations,
  getProjects,
} from "../../apis/studio";
import { holdsOne, type AttachRef, type AttachRole } from "../../context/CreateBarContext";
import { useUploads } from "../../hooks/useUploads";
import {
  DEFAULT_SORT,
  type Crumb,
  type FileEntry,
  type FolderEntry,
  type HeroImage,
  type MediaKind,
  type NodeRecord,
  type SortOrder,
} from "../../types";
import { MEDIA_GRID } from "../../utils/grid";
import { SortControl } from "../browse/SortControl";
import { TagFilter } from "../browse/TagFilter";
import { UploadButton } from "../browse/UploadButton";
import { UploadStatus } from "../browse/UploadStatus";
import { EmptyState } from "../common/EmptyState";
import { FilterBar } from "../common/FilterBar";
import { ArrowUpIcon, CheckIcon, FolderIcon } from "../common/icons";
import { LoadError } from "../common/LoadError";
import { SectionLoading } from "../common/SectionLoading";
import { SheetHandle } from "../common/SheetHandle";
import { EntityRow } from "../entity/EntityRow";
import { MediaThumb } from "../media/MediaThumb";
import { ROLE_WORDS } from "./roles";

const VIEW_FOLDERS = "folders";
const VIEW_MEDIA = "media";
type View = typeof VIEW_FOLDERS | typeof VIEW_MEDIA;

type EntityKind = "character" | "location" | "project";

/** A character, a location or a project, as much of it as the picker needs to open it. */
export interface PickerEntity {
  kind: EntityKind;
  id: string;
  name: string;
  /** The entity's root folder — the boundary the picker will not climb above. */
  root: string;
}

/**
 * Where the picker is standing.
 *
 * **Never the library root.** The tree above an entity is `characters/` and
 * `projects/` holding folders named by UUID, and walking it was the picker's
 * old top level — a screen of ids where a person expects names. The two lists
 * ARE the top level now: a character or a project is chosen by name, and the
 * file tree only begins inside it.
 */
type Place =
  | { kind: "characters" }
  | { kind: "locations" }
  | { kind: "projects" }
  | { kind: "entity"; entity: PickerEntity; folder: string };

/**
 * Which view an entity opens on.
 *
 * A character's folders are the person's own — `reference/`, `face/`, whatever
 * they made — so a readdir is how they find things. A project's are `runs/`
 * full of folders named by number: nothing in that tree is worth reading as a
 * tree, so a project opens on every picture under it. Both stay switchable.
 */
function defaultView(kind: EntityKind): View {
  return kind === "project" ? VIEW_MEDIA : VIEW_FOLDERS;
}

/**
 * The picker: a second sheet above the create sheet while a tile is
 * highlighted, so any picture in the library can be a reference, a start
 * frame or an end frame.
 *
 * **Pressing a picture attaches it; pressing it again takes it off.** There
 * is no chosen-list and no Add button: the tile in the sheet below IS the
 * list, and a one-image role replaces what it held. The picture stays marked
 * here so the same one is not sent twice — and the mark is a toggle, because
 * on a phone the sheet below is under this one, and its × cannot be reached
 * without closing the picker to find it.
 *
 * **Opens on the project it is creating in, in Media view** — every picture
 * under the project, newest first — and the `Characters` and `Projects` chips
 * are the way to any other entity, by name. Inside one, Folders is a readdir
 * and Media is the branch; a tag narrows either to the whole branch —
 * `default` inside a character is its identity images. Newest first
 * everywhere by default, and the sort is the person's to change.
 *
 * **Uploads, too.** A phone's camera roll is where most start frames live, so
 * the picker takes files into the folder it is standing on and attaches what
 * lands — the upload IS the pick.
 *
 * One kind, whichever view: every image role's tile stands for a picture, and
 * the clip tile for a video, so the listing is filtered to the one the role
 * takes — a clip cannot be a start frame, and a still cannot be the clip.
 *
 * **A bottom sheet on every screen.** 92dvh on a phone, 80dvh on a desk,
 * with its own handle; a one-picture role closes it on the pick, since the
 * tile it filled is what the sheet under it shows, and `Image refs` stays
 * open with a count in the title until it is dismissed — the handle, the
 * backdrop or Escape, the way every other sheet goes. A `Done` at the row's
 * end was one control more than that needed.
 *
 * It used to be a second card under the create sheet on a desk, capped at
 * 60vh, which was the right shape while the sheet sat at the foot of the
 * window and the picker hung up from it over the feed. With the sheet at
 * the top of the page the card hung down over the page's own heading, and
 * from the dock (`AttachDock`, the tiles kept on screen once the sheet has
 * scrolled away) there was nothing to hang it from at all — a drawer opens
 * the same from either, and the bottom sheet the phone already had is the
 * one shape that needs no second body. `dvh` rather than `vh`, so the top
 * of the sheet — the title row, the handle — is on the screen at all when
 * the browser's bars are showing.
 */
export function AttachPicker(props: PickerProps) {
  const words = ROLE_WORDS[props.role];
  const panel = useRef<HTMLDivElement>(null);
  return (
    <Drawer.Root
      side="bottom"
      open
      onOpenChange={(next: boolean) => {
        if (!next) props.onClose();
      }}
    >
      <Drawer.Backdrop />
      <Drawer.Panel ref={panel} className="flex h-[92dvh] flex-col rounded-t-lg pt-0 md:h-[80dvh]">
        <Drawer.Title className="sr-only">{words.choose}</Drawer.Title>
        <SheetHandle panel={panel} onDismiss={props.onClose} />
        <div
          className="flex min-h-0 flex-1 flex-col gap-2"
          data-attach-picker=""
          role="region"
          aria-label={words.choose}
        >
          <PickerBody {...props} />
        </div>
      </Drawer.Panel>
    </Drawer.Root>
  );
}

interface PickerProps {
  role: AttachRole;
  /** The project the sheet is creating in — where the picker opens. Null before it is known. */
  project: PickerEntity | null;
  /** Node ids already on the sheet, in any role. */
  attached: ReadonlySet<string>;
  /** How many the highlighted role holds — the count a phone's title shows while `Image refs` accumulates. */
  held?: number;
  /** The model's ceiling on that role, when it has one — the title reads `· 10 / 10`. */
  cap?: number | null;
  /**
   * Why the role can take no more, or null while it can. Set, every picture
   * not already on the sheet is disabled and carries the reason; the ones on
   * it stay pressable so a person can make room.
   */
  full?: string | null;
  onAttach: (ref: AttachRef) => void;
  /** A marked picture pressed again: take it off the sheet. */
  onDetach: (node: string) => void;
  onClose: () => void;
}

function PickerBody({
  role,
  project,
  attached,
  held = 0,
  cap = null,
  full = null,
  onAttach,
  onDetach,
  onClose,
}: PickerProps) {
  const [place, setPlace] = useState<Place>(() =>
    project ? { kind: "entity", entity: project, folder: project.root } : { kind: "projects" },
  );
  const [view, setView] = useState<View>(project ? defaultView(project.kind) : VIEW_MEDIA);
  const [sort, setSort] = useState<SortOrder>(DEFAULT_SORT);
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
  /** What this role is made of. */
  const wanted: MediaKind = role === "clip" ? "video" : "image";

  const entity = place.kind === "entity" ? place.entity : null;
  const folderId = place.kind === "entity" ? place.folder : null;

  /** Step into an entity, on the view its kind reads best in. */
  const open = useCallback((next: PickerEntity) => {
    setPlace({ kind: "entity", entity: next, folder: next.root });
    setView(defaultView(next.kind));
  }, []);

  useEffect(() => {
    if (folderId === null) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    // `kind` is what makes Media a search of the branch rather than a readdir —
    // see `getFolder`.
    getFolder({ node: folderId }, sort, {
      tag: asked ? asked.split(",") : [],
      kind: view === VIEW_MEDIA ? [wanted] : [],
    })
      .then((result) => {
        if (cancelled) return;
        const searched = result.depth === "all";
        // Folders are the way to pictures at one level; in a result gathered
        // from the whole branch they are on the way to nothing.
        setFolders(searched ? [] : result.folders);
        setFiles(result.files.filter((file) => file.kind === wanted));
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
  }, [folderId, asked, view, sort, attempt, wanted]);

  /**
   * The trail from the entity's root down, with the root labelled by name.
   *
   * The server's trail starts at the library root and passes through
   * `characters/` and a folder named by the entity's id; everything above the
   * root is the tree this picker exists to hide, and the root's stored name is
   * a UUID — see `FolderBrowser.boundaryLabel` for the same trim.
   */
  const trail = useMemo(() => {
    if (!entity) return [];
    const at = crumbs.findIndex((crumb) => crumb.id === entity.root);
    return at < 0 ? [] : crumbs.slice(at);
  }, [crumbs, entity]);
  const atRoot = entity !== null && folderId === entity.root;
  const parent = atRoot ? undefined : trail.at(-2)?.id;

  const words = ROLE_WORDS[role];
  // The sheet covers the tile it fills, so a one-picture role closes on the
  // pick and the tile is what the person sees next. A role that accumulates
  // stays open — the count in the title is the confirmation.
  const attach = useCallback(
    (file: Pick<FileEntry, "id" | "url" | "name">) => {
      // A picture picked out of a character's or a location's own tree is
      // attached AS that subject's, so the draft records who it is of and
      // where it is shot (`castOf`, `locationsOf`) without a second lookup.
      // A project's picture is an object: the project is already the run's.
      const provenance =
        entity?.kind === "character"
          ? { kind: "character" as const, character: entity.id }
          : entity?.kind === "location"
            ? { kind: "location" as const, location: entity.id }
            : { kind: "object" as const };
      onAttach({ node: file.id, url: file.url, name: file.name, ...provenance });
      if (holdsOne(role)) onClose();
    },
    [entity, onAttach, onClose, role],
  );

  /**
   * What landed is attached, then the listing catches up.
   *
   * A `NodeRecord` carries no signed URL and no kind, and a ref without a URL
   * draws as `Unavailable` until something re-signs it — so each is signed
   * first, and the answer's `kind` is what says whether it is what the role
   * takes. Only that kind attaches: a clip uploaded on an image tile — or a
   * still on the Source video tile — stays in the folder and is not a role.
   */
  const landed = useCallback(
    (nodes: NodeRecord[]) => {
      for (const node of nodes) {
        void getAsset(node.id)
          .then((asset) => {
            if (asset.kind === wanted) attach({ id: node.id, url: asset.url, name: node.name });
          })
          .catch(() => undefined);
      }
      setAttempt((n) => n + 1);
    },
    [attach, wanted],
  );
  const uploads = useUploads(folderId, landed);

  const empty = useMemo(() => folders.length === 0 && files.length === 0, [folders, files]);

  return (
    <>
      <div className="flex items-center gap-2">
        {/* The role's name — `Start frame` — rather than `Choose a start
            frame`: the row also holds the view switch, and on 390px the
            sentence was the thing that got cut. */}
        <Text as="span" variant="body" weight="medium" className="min-w-0 flex-1 truncate">
          {words.label}
          {!holdsOne(role) && (held > 0 || cap !== null) && (
            <Text as="span" variant="body" tone="muted">
              {cap === null ? ` · ${held}` : ` · ${held} / ${cap}`}
            </Text>
          )}
        </Text>
        {entity && (
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
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Chip
          size="sm"
          pressed={entity?.id === project?.id}
          disabled={project === null}
          onClick={() => project && open(project)}
        >
          Project
        </Chip>
        <Chip
          size="sm"
          pressed={place.kind === "characters"}
          onClick={() => setPlace({ kind: "characters" })}
        >
          Characters
        </Chip>
        <Chip
          size="sm"
          pressed={place.kind === "locations"}
          onClick={() => setPlace({ kind: "locations" })}
        >
          Locations
        </Chip>
        <Chip
          size="sm"
          pressed={place.kind === "projects"}
          onClick={() => setPlace({ kind: "projects" })}
        >
          Projects
        </Chip>
        {/* Not at the project's own root: the pressed `Project` chip already
            says where this is, and on a phone the one-crumb trail was a row
            of its own repeating it. A character's root keeps its crumb —
            no chip names it. */}
        {entity && !(atRoot && entity.id === project?.id) && (
          <Breadcrumbs.Root>
            {trail.map((crumb, index, all) => (
              <Breadcrumbs.Item
                key={crumb.id}
                current={index === all.length - 1}
                href="#"
                onClick={(event: React.MouseEvent) => {
                  event.preventDefault();
                  setPlace({ kind: "entity", entity, folder: crumb.id });
                }}
              >
                {index === 0 ? entity.name : crumb.name}
              </Breadcrumbs.Item>
            ))}
          </Breadcrumbs.Root>
        )}
      </div>

      {entity && (
        <>
          {/* One line: the sort, Upload, and the tag filter folded behind
              `Filter` the way the Files page folds it — a count badge says
              when a tag is narrowing the grid. It used to be an open input
              with a note under it, three lines on a phone above a grid this
              sheet exists to show; the tags are used seldom enough that a
              press to reach them costs less than the rows they took.

              The note about scope is for Folders only: Media is the branch
              by definition, so "everything under it" says nothing there. */}
          <div className="flex flex-wrap items-center gap-2">
            <SortControl value={sort} onChange={setSort} />
            <UploadButton onFiles={uploads.start} disabled={uploads.active} />
            <FilterBar activeCount={tags.length} onClear={() => setTags([])}>
              <TagFilter
                value={tags}
                onChange={setTags}
                searching={deep && view === VIEW_FOLDERS}
              />
            </FilterBar>
          </div>
          <UploadStatus items={uploads.items} onClearFinished={uploads.clearFinished} />
        </>
      )}

      <div className="min-h-32 flex-1 overflow-y-auto rounded-md bg-fill-faint">
        {place.kind === "characters" && (
          <EntityList kind="character" onOpen={open} />
        )}
        {place.kind === "locations" && <EntityList kind="location" onOpen={open} />}
        {place.kind === "projects" && <EntityList kind="project" onOpen={open} />}
        {entity &&
          (error ? (
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
                <FolderRow
                  icon={<ArrowUpIcon className={ROW_GLYPH} />}
                  name="Up one folder"
                  onClick={() => setPlace({ kind: "entity", entity, folder: parent })}
                />
              )}
              {folders.map((folder) => (
                <FolderRow
                  key={folder.id}
                  icon={<FolderIcon className={ROW_GLYPH} />}
                  name={folder.name}
                  onClick={() => setPlace({ kind: "entity", entity, folder: folder.id })}
                />
              ))}
              {files.length > 0 && (
                <div className={`${MEDIA_GRID} p-2`}>
                  {files.map((file) => {
                    const on = attached.has(file.id);
                    const blocked = !on && full !== null;
                    return (
                      <Button
                        key={file.id}
                        intent="secondary"
                        size="sm"
                        aria-pressed={on}
                        aria-label={on ? `Remove ${file.name}` : `Attach ${file.name}`}
                        title={blocked ? full : file.name}
                        disabled={blocked}
                        className={`relative h-auto flex-col items-stretch gap-1 rounded-md bg-transparent p-1 text-left
                                    hover:bg-fill active:bg-fill-active ${on ? "ring-2 ring-primary" : ""}`}
                        onClick={() => (on ? onDetach(file.id) : attach(file))}
                      >
                        <MediaThumb
                          nodeId={file.id}
                          url={file.url}
                          poster={file.poster}
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
          ))}
      </div>
    </>
  );
}

const ROW_GLYPH = "size-5 shrink-0 fill-none stroke-muted stroke-[1.5]";

/**
 * Every character, every location, or every project, by name — the picker's top level.
 *
 * Fetched when the list is shown rather than when the picker opens: the
 * picker opens inside the project it was raised from, and most picks never
 * leave it.
 */
function EntityList({
  kind,
  onOpen,
}: {
  kind: EntityKind;
  onOpen: (entity: PickerEntity) => void;
}) {
  const [rows, setRows] = useState<Array<PickerEntity & { hero: HeroImage | null }> | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    const list =
      kind === "character" ? getCharacters() : kind === "location" ? getLocations() : getProjects();
    list
      .then((listed) => {
        if (cancelled) return;
        setRows(
          listed.flatMap((each) =>
            // A summary without a root is a capture that predates the field;
            // there is nothing to open, so it is not offered.
            each.root
              ? [{ kind, id: each.id, name: each.name, root: each.root, hero: each.hero }]
              : [],
          ),
        );
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [kind, attempt]);

  const noun = `${kind}s`;
  if (error)
    return <LoadError what={noun} message={error} onRetry={() => setAttempt((n) => n + 1)} />;
  if (rows === null) return <SectionLoading label={`Loading ${noun}`} />;
  if (rows.length === 0) return <EmptyState title={`No ${noun} yet.`} className="p-3" />;

  return (
    <div className="flex flex-col" data-entity-list={noun}>
      {rows.map((row) => (
        <EntityRow
          key={row.id}
          title={row.name}
          thumb={row.hero ? { node: row.hero.node, url: row.hero.url, poster: row.hero.poster } : { placeholder: kind }}
          onOpen={() => onOpen(row)}
        />
      ))}
    </div>
  );
}

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
  return `h-7 rounded-md px-2.5 text-sm ${
    on
      ? "bg-fill-active text-ink hover:bg-fill-active active:bg-fill-active"
      : "text-muted hover:bg-fill hover:text-ink"
  }`;
}
