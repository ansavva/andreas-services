import { useCallback } from "react";

import { getProject } from "../apis/studio";
import { useResource } from "./useResource";

/**
 * A project's name, for the trail a scene or a movie draws under the tabs.
 *
 * **Both carry their project's *id* and nothing else**, so the name costs a
 * request — the same one `ProjectBarOn` makes for the bar above, so it is
 * served from the cache and costs nothing extra. It answers the generic word
 * while in flight rather than nothing, so the trail does not appear a beat
 * after the page; and it survives a failure, because a crumb that vanishes
 * because a lookup 404'd takes the way out with it.
 */
export function useProjectName(projectId: string): string {
  const load = useCallback(() => getProject(projectId), [projectId]);
  const { data } = useResource(projectId ? ["project", projectId] : null, load);
  return data?.name || "Project";
}
