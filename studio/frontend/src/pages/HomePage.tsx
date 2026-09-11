import { CharactersSection, ProjectsSection } from "../components/entity/EntitySections";
import { FavoritesSection } from "../components/favorites/FavoritesSection";
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
 * **Favorites lead, and they are the one grid of media home draws.** The Recent
 * grid answered "what did the last hour produce" and cost a walk of the whole
 * library to do it; this answers "what did I keep", and it costs one query on
 * one partition — the caller's own — because a favorite is a row filed under
 * the person rather than a property of the library to be searched for. The
 * first two rows are here and `/favorites` has the rest.
 *
 * **The three lists are components, not markup here.** `/favorites`,
 * `/characters` and `/projects` are real screens the sidebar links to, and they
 * render exactly these — so home is where all three meet rather than the only
 * place any of them exists.
 */
export function HomePage() {
  return (
    <>
      <PageBar title="Home" />

      <FavoritesSection variant="preview" />
      <CharactersSection />
      <ProjectsSection />
    </>
  );
}
