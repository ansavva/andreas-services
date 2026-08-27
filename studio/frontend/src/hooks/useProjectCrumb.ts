import { useCallback, useMemo } from "react";

import { getProject } from "../apis/studio";
import type { Crumb } from "../components/layout/PageBar";
import { PROJECTS_PATH, projectPath } from "../utils/location";
import { useResource } from "./useResource";

/**
 * The trail above a run, a scene or a movie: Projects › <the project>.
 *
 * **All three carry their project's *id* and nothing else**, so the name costs
 * a request. It is worth one: the crumb replaced a `← Project` button, and a
 * button that says "Project" is a way back, while a crumb that says the
 * project's name is also an answer to "where am I". A person landing on a
 * pasted run link has no other way to find out.
 *
 * It renders the generic label while the request is in flight rather than
 * nothing, so the trail does not appear a beat after the page and shove the
 * title down. Same reason it survives a failure: a crumb that vanishes because
 * a lookup 404'd takes the way out with it.
 */
export function useProjectCrumb(projectId: string): Crumb[] {
  const load = useCallback(() => getProject(projectId), [projectId]);
  const { data } = useResource(projectId ? ["project", projectId] : null, load);

  return useMemo(
    () => [
      { label: "Projects", to: PROJECTS_PATH },
      { label: data?.title || data?.slug || "Project", to: projectPath(projectId) },
    ],
    [data, projectId],
  );
}
