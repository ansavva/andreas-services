import { useCallback, useMemo, useState } from "react";

import { Chip, IconButton } from "@ansavva/design-system";

import {
  getCharacterSelection,
  getCharacters,
  getProjectInputs,
  getRuns,
} from "../../apis/studio";
import type { AttachRef } from "../../context/CreateBarContext";
import { useResource } from "../../hooks/useResource";
import { EmptyState } from "../common/EmptyState";
import { CheckIcon, CloseIcon, PersonIcon } from "../common/icons";
import { LoadError } from "../common/LoadError";
import { SectionLoading } from "../common/SectionLoading";

/**
 * Where an image for the highlighted role comes from.
 *
 * Three kinds of source, as a chip row: each of the project's cast (their
 * identity images — what `GET /api/characters/<id>/selection` answers, the
 * same set a run would be shown), the project's input pool, and the outputs
 * of this project's recent runs. Every tile attaches to the highlighted role
 * on one press; a tile already attached shows a check and presses off nothing
 * — taking an image off is the × on its thumb in the strip.
 *
 * **The cast chip carries an avatar.** The character's hero, off the same
 * `GET /api/characters` listing the sidebar and the search already hold, or
 * a dashed placeholder when it has none — a character with no picture yet is
 * a real state, and the chip says so rather than drawing a broken image.
 */
export function CreateDrawer({
  projectId,
  cast,
  attached,
  onAttach,
  onClose,
}: {
  projectId: string;
  cast: ReadonlyArray<{ id: string; name: string }>;
  /** Node ids already on the bar, in any role. */
  attached: ReadonlySet<string>;
  onAttach: (ref: AttachRef) => void;
  onClose: () => void;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const source = picked ?? (cast[0] ? `char:${cast[0].id}` : "outputs");

  const characters = useResource(
    ["characters"],
    useCallback(() => getCharacters(), []),
  );
  const heroes = useMemo(
    () =>
      new Map(
        (characters.data ?? []).map((each) => [
          each.id,
          each.hero?.url ?? null,
        ]),
      ),
    [characters.data],
  );

  return (
    <div className="relative flex flex-col gap-3 p-4" data-create-drawer="">
      <IconButton
        size="sm"
        label="Close"
        className="absolute right-3 top-3 rounded-none"
        onClick={onClose}
      >
        <CloseIcon />
      </IconButton>

      <div
        className="flex flex-wrap gap-1.5 pr-10"
        role="tablist"
        aria-label="Image source"
      >
        {cast.map((each) => {
          const hero = heroes.get(each.id) ?? null;
          const value = `char:${each.id}`;
          return (
            <Chip
              key={each.id}
              role="tab"
              aria-selected={source === value}
              pressed={source === value}
              size="sm"
              className="gap-2 rounded-none pl-1.5"
              onClick={() => setPicked(value)}
            >
              {hero ? (
                <img
                  src={hero}
                  alt=""
                  className="size-[22px] shrink-0 border border-line object-cover"
                />
              ) : (
                <span className="inline-flex size-[22px] shrink-0 items-center justify-center border border-dashed border-muted text-muted">
                  <PersonIcon className="size-3 fill-none stroke-current stroke-[1.5]" />
                </span>
              )}
              {each.name} · identity
            </Chip>
          );
        })}
        <Chip
          role="tab"
          aria-selected={source === "inputs"}
          pressed={source === "inputs"}
          size="sm"
          className="rounded-none"
          onClick={() => setPicked("inputs")}
        >
          Inputs
        </Chip>
        <Chip
          role="tab"
          aria-selected={source === "outputs"}
          pressed={source === "outputs"}
          size="sm"
          className="rounded-none"
          onClick={() => setPicked("outputs")}
        >
          This project's outputs
        </Chip>
      </div>

      {source.startsWith("char:") ? (
        <CastTiles
          characterId={source.slice(5)}
          attached={attached}
          onAttach={onAttach}
        />
      ) : source === "inputs" ? (
        <InputTiles
          projectId={projectId}
          attached={attached}
          onAttach={onAttach}
        />
      ) : (
        <OutputTiles
          projectId={projectId}
          attached={attached}
          onAttach={onAttach}
        />
      )}
    </div>
  );
}

interface TilesProps {
  attached: ReadonlySet<string>;
  onAttach: (ref: AttachRef) => void;
}

function CastTiles({
  characterId,
  ...rest
}: TilesProps & { characterId: string }) {
  const selection = useResource(
    ["character-selection", characterId],
    useCallback(() => getCharacterSelection(characterId), [characterId]),
  );
  if (selection.error) {
    return (
      <LoadError
        what="the character's images"
        message={selection.error}
        onRetry={selection.reload}
      />
    );
  }
  if (selection.loading || !selection.data)
    return <SectionLoading label="Loading identity images" />;

  const refs: AttachRef[] = selection.data.selection.flatMap((each) =>
    each.url
      ? [
          {
            node: each.node,
            url: each.url,
            name: each.name ?? each.node,
            kind: "character" as const,
            character: characterId,
          },
        ]
      : [],
  );
  return <Tiles refs={refs} empty="No identity images yet." {...rest} />;
}

function InputTiles({
  projectId,
  ...rest
}: TilesProps & { projectId: string }) {
  const inputs = useResource(
    ["project-inputs", projectId],
    useCallback(() => getProjectInputs(projectId), [projectId]),
  );
  if (inputs.error) {
    return (
      <LoadError
        what="the input pool"
        message={inputs.error}
        onRetry={inputs.reload}
      />
    );
  }
  if (inputs.loading || !inputs.data)
    return <SectionLoading label="Loading the input pool" />;

  const refs: AttachRef[] = inputs.data.inputs.flatMap((each) =>
    each.url && isImageName(each.name)
      ? [
          {
            node: each.id,
            url: each.url,
            name: each.name,
            kind: "input-pool" as const,
          },
        ]
      : [],
  );
  return <Tiles refs={refs} empty="No inputs yet." {...rest} />;
}

function OutputTiles({
  projectId,
  ...rest
}: TilesProps & { projectId: string }) {
  const feed = useResource(
    ["runs", "feed", projectId],
    useCallback(
      () => getRuns({ project: projectId, view: "feed" }),
      [projectId],
    ),
  );
  if (feed.error) {
    return (
      <LoadError
        what="the project's outputs"
        message={feed.error}
        onRetry={feed.reload}
      />
    );
  }
  if (feed.loading || !feed.data)
    return <SectionLoading label="Loading outputs" />;

  // Images only: a reference, a start frame or an edit is a picture, and a
  // clip cannot be one. The feed is newest first, so the tiles are too.
  const refs: AttachRef[] = feed.data.runs.flatMap((run) =>
    run.outputs.flatMap((output, index) =>
      isImage(output.content_type, output.name)
        ? [
            {
              node: output.node,
              url: output.url,
              name: output.name,
              kind: "run" as const,
              run: run.id,
              output: index + 1,
            },
          ]
        : [],
    ),
  );
  return <Tiles refs={refs} empty="No outputs yet." {...rest} />;
}

/** Mirrors `keys.IMAGE_EXTENSIONS` — what the API classifies as an image. */
const IMAGE_EXTENSIONS = /\.(jpe?g|png|webp|gif|bmp|tiff?)$/i;

function isImageName(name: string): boolean {
  return IMAGE_EXTENSIONS.test(name);
}

function isImage(
  contentType: string | null | undefined,
  name: string,
): boolean {
  if (contentType) return contentType.startsWith("image/");
  return isImageName(name);
}

/**
 * The tiles. Each is one `Chip` — a real button with `aria-pressed` — holding
 * the picture and a caption saying where it came from.
 */
function Tiles({
  refs,
  empty,
  attached,
  onAttach,
}: TilesProps & { refs: AttachRef[]; empty: string }) {
  if (refs.length === 0) return <EmptyState title={empty} />;
  return (
    <div className="flex gap-2 overflow-x-auto">
      {refs.map((ref) => {
        const on = attached.has(ref.node);
        return (
          <Chip
            key={ref.node}
            pressed={on}
            size="sm"
            className="relative h-40 w-[7.5rem] shrink-0 overflow-hidden rounded-none p-0"
            aria-label={`Attach ${ref.name}`}
            onClick={() => onAttach(ref)}
          >
            <img src={ref.url} alt="" className="size-full object-cover" />
            {on && (
              <span className="absolute left-1.5 top-1.5 inline-flex size-5 items-center justify-center bg-primary text-primary-text">
                <CheckIcon className="size-3 fill-none stroke-current stroke-[2.5]" />
              </span>
            )}
            <span className="absolute inset-x-0 bottom-0 truncate bg-overlay-scrim px-1.5 py-1 text-left font-mono text-[11px] text-overlay-ink">
              {captionOf(ref)}
            </span>
          </Chip>
        );
      })}
    </div>
  );
}

/** `run 7f3a · out-2.png`, `input · coat-ref.jpg`, `identity · face-01.png`. */
export function captionOf(ref: AttachRef): string {
  switch (ref.kind) {
    case "run":
      return `run ${(ref.run ?? "").replace(/^run-/, "").slice(0, 4)} · ${ref.name}`;
    case "input-pool":
      return `input · ${ref.name}`;
    case "character":
      return `identity · ${ref.name}`;
    case "object":
      return ref.name;
  }
}
