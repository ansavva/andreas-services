import { FavoritesSection } from "../components/favorites/FavoritesSection";
import { PageBar } from "../components/layout/PageBar";

/**
 * Everything this person has picked out, newest first.
 *
 * **A screen of its own as well as the top of home**, the same bargain
 * `/characters` and `/projects` struck: home leads with the first two rows
 * because that is what studio should open on, and a list you have to scroll to
 * reach is not navigation. The sidebar links here.
 *
 * The grid is `FavoritesSection` — one component at two sizes — so the page and
 * home cannot drift into two subtly different favorites screens.
 */
export function FavoritesPage() {
  return (
    <>
      <PageBar title="Favorites" />
      <FavoritesSection variant="full" />
    </>
  );
}
