import { useCallback } from "react";

import { Text } from "@ansavva/design-system";

import { getCharacters } from "../apis/studio";
import { CreateEntityDialog } from "../components/entity/CreateEntityDialog";
import { CharactersSection } from "../components/entity/EntitySections";
import { PageBar } from "../components/layout/PageBar";
import { useResource } from "../hooks/useResource";

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
 *
 * **The count lives in the bar now, not under it twice.** `PageBar`'s title
 * and `CharactersSection`'s own heading used to both say "Characters",
 * stacked — so this reads the same `["characters"]` query the section reads
 * (React Query dedupes the two into one request) purely for the count, and
 * the section renders with `heading={false}`.
 */
export function CharactersPage() {
  const { data } = useResource(["characters"], useCallback(() => getCharacters(), []));
  const count = data?.length;

  return (
    <>
      <PageBar
        title="Characters"
        meta={
          count !== undefined && (
            <Text variant="caption" family="mono" tone="muted">
              {count} {count === 1 ? "character" : "characters"}
            </Text>
          )
        }
        primary={<CreateEntityDialog kind="character" />}
      />
      <CharactersSection hasPrimary heading={false} />
    </>
  );
}
