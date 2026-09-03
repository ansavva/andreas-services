import { CreateEntityDialog } from "../components/entity/CreateEntityDialog";
import { ProjectsSection } from "../components/entity/EntitySections";
import { PageBar } from "../components/layout/PageBar";

/** Every project. The sibling of `CharactersPage` — see there for the reasoning. */
export function ProjectsPage() {
  return (
    <>
      <PageBar title="Projects" primary={<CreateEntityDialog kind="project" />} />
      <ProjectsSection hasPrimary />
    </>
  );
}
