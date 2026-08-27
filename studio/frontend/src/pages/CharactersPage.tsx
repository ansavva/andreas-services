import { CharactersSection } from "../components/entity/EntitySections";

/**
 * Every character, and nothing else.
 *
 * Home lists these too, above two other sections. This is not that list
 * duplicated — it is the same component — and it exists because a section you
 * have to scroll past two others to reach is not somewhere you can *go*. The
 * header links here.
 *
 * No `PageBar`: the section's own heading names the screen and the header's
 * active link says where you are, so a breadcrumb here would have one crumb
 * pointing at the page you are standing on.
 */
export function CharactersPage() {
  return <CharactersSection />;
}
