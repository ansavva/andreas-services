import { useCallback } from "react";

import { Text } from "@ansavva/design-system";

import { getLocations } from "../apis/studio";
import { CreateEntityDialog } from "../components/entity/CreateEntityDialog";
import { LocationsSection } from "../components/entity/EntitySections";
import { PageBar } from "../components/layout/PageBar";
import { useResource } from "../hooks/useResource";

/**
 * Every location, and nothing else — `CharactersPage` for the places a frame
 * is shot in. The same section home draws, reachable from the sidebar, with
 * the count in the bar rather than under it twice.
 */
export function LocationsPage() {
  const { data } = useResource(["locations"], useCallback(() => getLocations(), []));
  const count = data?.length;

  return (
    <>
      <PageBar
        title="Locations"
        meta={
          count !== undefined && (
            <Text variant="caption" family="mono" tone="muted">
              {count} {count === 1 ? "location" : "locations"}
            </Text>
          )
        }
        primary={<CreateEntityDialog kind="location" />}
      />
      <LocationsSection hasPrimary heading={false} />
    </>
  );
}
