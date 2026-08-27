import { CreateEntityDialog } from "../components/entity/CreateEntityDialog";
import { ProjectsSection } from "../components/entity/EntitySections";

/** Every project. The sibling of `CharactersPage` — see there for the reasoning. */
export function ProjectsPage() {
  return (
    <ProjectsSection action={<CreateEntityDialog kind="project" />} />
  );
}
