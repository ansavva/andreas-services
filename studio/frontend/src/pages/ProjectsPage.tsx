import { useCallback } from "react";

import { Text } from "@ansavva/design-system";

import { getProjects } from "../apis/studio";
import { CreateEntityDialog } from "../components/entity/CreateEntityDialog";
import { ProjectsSection } from "../components/entity/EntitySections";
import { PageBar } from "../components/layout/PageBar";
import { useResource } from "../hooks/useResource";

/**
 * Every project. The sibling of `CharactersPage` — see there for the
 * reasoning, including why the count reads the same query the section does
 * rather than the section's own heading saying it twice.
 */
export function ProjectsPage() {
  const { data } = useResource(["projects"], useCallback(() => getProjects(), []));
  const count = data?.length;

  return (
    <>
      <PageBar
        title="Projects"
        meta={
          count !== undefined && (
            <Text variant="caption" family="mono" tone="muted">
              {count} {count === 1 ? "project" : "projects"}
            </Text>
          )
        }
        primary={<CreateEntityDialog kind="project" />}
      />
      <ProjectsSection hasPrimary heading={false} />
    </>
  );
}
