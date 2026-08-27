import { useCallback, useMemo } from "react";

import { getAsset, getNode, getReferences, getRun, getScene } from "../apis/studio";
import type { FileEntry, RunAsset, Shot, SortOrder } from "../types";
import type { ViewerSource } from "../utils/location";
import { useReel } from "./useReel";
import { useResource } from "./useResource";
import { useTree } from "./useTree";

/**
 * A pointer, as a listing entry.
 *
 * Runs, scenes and movies describe their media as `{node, name, url,
 * content_type, size}` while the file layer describes it as a `FileEntry`, and
 * the viewer only knows the second shape. This is the one place the two meet —
 * writing the adapter once is what lets a storyboard frame and a folder tile be
 * the same screen.
 *
 * `key` gets the name rather than a path: nothing in the viewer resolves it,
 * and a pointer carries no ancestry to build one from.
 */
function fromAsset(asset: RunAsset): FileEntry {
  const type = asset.content_type ?? "";
  return {
    id: asset.node,
    key: asset.name,
    name: asset.name,
    size: asset.size ?? 0,
    content_type: type,
    last_modified: "",
    kind: type.startsWith("video/") ? "video" : type.startsWith("image/") ? "image" : "other",
    url: asset.url ?? "",
  };
}

/** Only what can actually be drawn. A panel that was planned and never rendered has no url. */
const drawable = (entry: FileEntry) =>
  Boolean(entry.url) && (entry.kind === "image" || entry.kind === "video");

/**
 * Every frame a shot touches, in the order the board draws them.
 *
 * The handoff frame first, then the panels by number, then the clip that came
 * out — which is the order a person reads a shot in, so it is the order
 * scrolling moves through.
 */
function shotAssets(shot: Shot): RunAsset[] {
  const handoff = shot.continues !== false ? shot.opens_on?.frame : undefined;
  const panels = [...(shot.panels ?? [])]
    .sort((a, b) => a.n - b.n)
    .map((panel) => panel.image)
    .filter((image): image is RunAsset => Boolean(image));

  return [
    ...(handoff ? [handoff] : []),
    ...panels,
    ...(shot.motion?.reference_assets ?? []),
    ...(shot.clip ? [shot.clip] : []),
  ];
}

export interface ViewerFeed {
  /** The drawable sequence — what the reel scrolls through. */
  items: FileEntry[];
  /**
   * Everything the source holds, media or not.
   *
   * A folder contains `prompt.json` and `profile.yaml` as well as frames, and
   * `/o/<id>` is their address too — the text viewer has always been reached
   * that way. `items` cannot carry them (a reel of a YAML file is nothing), so
   * the viewer picks the open node out of this and decides which screen it is.
   */
  all: FileEntry[];
  loading: boolean;
  error: string | null;
  exhausted: boolean;
  truncated: boolean;
  loadMore?: () => void;
  /** Re-read the source after a write that changed it. */
  reload: () => void;
}

/**
 * What the viewer scrolls through, decided by the address.
 *
 * **The whole point of this rework is that the neighbours differ.** A file
 * opened from a folder should scroll through that folder; opened from a run,
 * through that run's frames; opened from a storyboard, through the board. Before
 * this, all three meant "the folder browser with the file open over it", so
 * opening a run's output left the run.
 *
 * All four sources are subscribed on every render and three of them are idle,
 * because hooks cannot be called conditionally. Each is off unless its kind is
 * selected — `useTree` fetches nothing for an `undefined` folder, `useReel`
 * takes an `enabled`, and `useResource` takes a null loader — so an idle source
 * costs a closure and no request.
 */
export function useViewerFeed(
  source: ViewerSource | null,
  nodeId: string,
  sort: SortOrder,
): ViewerFeed {
  const kind = source?.in ?? "alone";

  const tree = useTree(kind === "f" && source ? (source.id as string | null) : undefined, sort);
  const reel = useReel(
    kind === "recursive" && source ? (source.id as string | null) : null,
    sort,
    kind === "recursive",
  );

  /**
   * The entity sources, and the lone file.
   *
   * One loader rather than three hooks: they differ only in which request they
   * make and how its answer flattens, and `useResource` already owns the three
   * states around that.
   */
  const load = useCallback(async (): Promise<FileEntry[]> => {
    if (!source) {
      // A share link with no context. The file is fetched on its own and the
      // reel holds exactly one pane — which is the honest rendering of "this
      // link names a file and nothing about where it sits".
      const [node, asset] = await Promise.all([getNode(nodeId), getAsset(nodeId)]);
      const type = node.content_type ?? "";
      return [
        {
          id: node.id,
          key: node.name,
          name: node.name,
          size: node.size ?? 0,
          content_type: type,
          last_modified: node.updated_at ?? node.created_at,
          kind: type.startsWith("video/") ? "video" : type.startsWith("image/") ? "image" : "other",
          url: asset.url,
          description: node.description,
          tags: node.tags,
        },
      ];
    }

    if (source.in === "run") {
      const run = await getRun(source.id);
      // Outputs first, then everything it was given. Both grids on the run page
      // open into this, so both have to be in it — and what came out is what a
      // person is usually looking at.
      const bindings = Object.values(run.bindings).flat();
      return dedupe([...run.outputs, ...bindings].map(fromAsset));
    }

    if (source.in === "scene") {
      const scene = await getScene(source.id);
      const shots = [...scene.shots].sort((a, b) => a.order - b.order);
      const cut = scene.output ? [scene.output] : [];
      return dedupe([...cut, ...shots.flatMap(shotAssets)].map(fromAsset));
    }

    if (source.in === "refs") {
      // The character's reference pool, in group and then in board order, which
      // is the order a shoot would send them in. A `REF#` row carries the node
      // id beside the file, so the two halves are joined here rather than in
      // the adapter — `entry.file` alone does not know which node it is.
      const grouped = await getReferences(source.id);
      return dedupe(
        Object.values(grouped.groups).flatMap((entries) =>
          entries.map((entry) => fromAsset({ node: entry.node, ...entry.file })),
        ),
      );
    }

    // `f` and `recursive` never reach here — `useResource` is handed a null
    // loader for them, and the tree and the reel answer instead.
    return [];
  }, [nodeId, source]);

  const entity = useResource(kind === "f" || kind === "recursive" ? null : load);

  const media = useMemo(
    () => (tree.data?.files ?? []).filter(drawable),
    [tree.data],
  );

  if (kind === "f") {
    return {
      items: media,
      all: tree.data?.files ?? [],
      loading: tree.loading,
      error: tree.error,
      exhausted: true,
      truncated: false,
      reload: tree.reload,
    };
  }

  if (kind === "recursive") {
    return {
      // The reel walk is media by construction — the API filters to image and
      // video — so there is nothing else to carry.
      items: reel.items,
      all: reel.items,
      loading: reel.loading,
      error: reel.error,
      exhausted: reel.exhausted,
      truncated: reel.truncated,
      loadMore: reel.loadMore,
      reload: () => undefined,
    };
  }

  return {
    items: (entity.data ?? []).filter(drawable),
    all: entity.data ?? [],
    loading: entity.loading,
    error: entity.error,
    exhausted: true,
    truncated: false,
    reload: entity.reload,
  };
}

/**
 * First mention of a node wins.
 *
 * A board draws the same frame more than once on purpose — a panel demoted to a
 * reference is both — and the viewer is a *sequence*, where the same pane twice
 * is a scroll that appears to go nowhere.
 */
function dedupe(entries: FileEntry[]): FileEntry[] {
  const seen = new Set<string>();
  return entries.filter((entry) => !seen.has(entry.id) && seen.add(entry.id));
}
