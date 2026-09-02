import { useCallback } from "react";
import { useNavigate } from "react-router-dom";

import { getNodeOwner } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { characterPath, moviePath, projectPath, scenePath } from "../../utils/location";

/**
 * What a file belongs to, for a link that arrived with no context.
 *
 * `/o/<id>` on its own is what a share link usually is — the id is the durable
 * half and `?in=` is a convenience for whoever was browsing. Opened cold it
 * showed one frame and offered nothing but Close, which went home: the file was
 * on screen and where it lived was unanswerable.
 *
 * `GET /api/nodes/<id>/owner` walks the ancestry and says which entity it sits
 * in. It has existed since involvement became rows and this is its first caller.
 *
 * **Only rendered when there is no context**, because everywhere else the
 * neighbours already say where you are — a run's frames are obviously the run's.
 * Fetching it regardless would be a request per viewer open to draw nothing.
 */
export function OwnerLink({ nodeId }: { nodeId: string }) {
  const navigate = useNavigate();
  const load = useCallback(() => getNodeOwner(nodeId), [nodeId]);
  const { data } = useResource(nodeId ? ["owner", nodeId] : null, load);

  const to = data ? pathFor(data.kind, data.id) : null;
  if (!data || !to) return null;

  return (
    <button
      type="button"
      onClick={() => navigate(to)}
      className="rounded-none text-left text-muted underline-offset-2 hover:text-ink hover:underline
                 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      {/* The slug, because that is what a person types at the CLI and the two
          must read as the same thing. A run has none — it is a machine event —
          so it falls back to the word. */}
      <span className="font-body text-xs">in {data.name ?? data.kind}</span>
    </button>
  );
}

/**
 * Where an owner is reached.
 *
 * **A run and a movie are owners this cannot link to**, and that is not an
 * oversight: `runPath` needs the project id as well, which the owner walk does
 * not report, and a movie's own page is reachable from its project. Returning
 * `null` renders nothing rather than a link that lands somewhere wrong.
 */
function pathFor(kind: string, id: string): string | null {
  if (kind === "character") return characterPath(id);
  if (kind === "project") return projectPath(id);
  if (kind === "scene") return scenePath(id);
  if (kind === "movie") return moviePath(id);
  return null;
}
