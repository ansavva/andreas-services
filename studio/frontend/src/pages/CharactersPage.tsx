import { CreateEntityDialog } from "../components/entity/CreateEntityDialog";
import { CharactersSection } from "../components/entity/EntitySections";
import { PageBar } from "../components/layout/PageBar";

/**
 * Every character, and nothing else.
 *
 * Home lists these too, above two other sections. This is not that list
 * duplicated — it is the same component — and it exists because a section you
 * have to scroll past two others to reach is not somewhere you can *go*. The
 * header links here.
 *
 * No crumb: the header's active link already says where you are, and one
 * crumb pointing at the page you are standing on says nothing.
 */
export function CharactersPage() {
  return (
    <>
      <PageBar title="Characters" primary={<CreateEntityDialog kind="character" />} />
      <CharactersSection hasPrimary />
    </>
  );
}
