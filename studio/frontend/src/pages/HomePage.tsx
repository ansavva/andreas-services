import { CharactersSection, ProjectsSection } from "../components/entity/EntitySections";
import { PageBar } from "../components/layout/PageBar";

/**
 * What studio opens on: who there is, and what is being made.
 *
 * **This is the reversal the entity model bought.** Studio's users are not files
 * — they are characters and projects — and until now the app could not say so,
 * because both were a folder name with a document inside it and the app was
 * forbidden to read the document. They are rows with ids now, so the first screen
 * can be the two lists instead of a listing of the library root.
 *
 * **There is no Recent grid any more.** It answered "what did the last hour
 * produce" with a walk of the whole library — `/api/reel` reads the branch,
 * sorts and slices, so twelve tiles cost the enumeration of everything — and
 * the project feed answers the same question per project, where the answer is
 * cheap and has a plan beside it. The file tree is one click away at `/f`.
 *
 * **The two lists are components, not markup here.** `/characters` and
 * `/projects` are real screens the sidebar links to, and they render exactly
 * these — so home is where both meet rather than the only place either exists.
 */
export function HomePage() {
  return (
    <>
      <PageBar title="Home" />

      <CharactersSection />
      <ProjectsSection />
    </>
  );
}
