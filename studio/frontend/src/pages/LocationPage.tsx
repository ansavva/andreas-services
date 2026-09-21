import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Tabs } from "@ansavva/design-system";

import { LoadError } from "../components/common/LoadError";
import { PageLoading } from "../components/common/PageLoading";
import { ApiError } from "../apis/client";
import {
  deleteLocation,
  getLocation,
  getLocationProfileTemplate,
  patchLocation,
  setLocationProfile,
} from "../apis/studio";
import { FolderTab } from "../components/browse/FolderTab";
import { PageBar, useCopyLinkItem } from "../components/layout/PageBar";
import { ProfileForm } from "../components/character/ProfileForm";
import { LOCATION_SCHEMA } from "../components/character/profileSchemas";
import { useResource } from "../hooks/useResource";
import { LOCATIONS_PATH } from "../utils/location";
import type { LocationIdentity, LocationProfile, LocationRecord } from "../types";
import { useSearchParamState } from "../hooks/useSearchParamState";
import { ConfirmDestroyDialog } from "../components/common/ConfirmDestroyDialog";
import { TrashIcon } from "../components/common/icons";

/**
 * One location: what the place is, what it looks like, and everything filed
 * under it.
 *
 * **`CharacterPage` with a room's bible.** A location is the same record as a
 * character — a name, a `rev`, a `profile` map, a root folder whose images
 * carry the `default` tag — served under `/api/locations`, so this page is
 * that one with the location wrappers and `LOCATION_SCHEMA` handed to the
 * same form. Two tabs for the same reason it has two: Profile is the bible
 * and Files is the tree, and identity is a tag inside Files rather than a
 * third place.
 *
 * The two writes chain exactly as they do there — patch the record, take
 * `rev` off what came back, put the profile with it — because both are
 * compare-and-swap on one row and a parallel pair would 409 against itself.
 */
export function LocationPage() {
  const { locationId = "" } = useParams();
  const copyLink = useCopyLinkItem();
  const navigate = useNavigate();

  const [tab, setTab] = useSearchParamState("tab", "profile");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const load = useCallback(() => getLocation(locationId), [locationId]);
  const location = useResource(["location", locationId], load);
  const template = useResource(["location-profile-template"], getLocationProfileTemplate);

  const [conflict, setConflict] = useState<string | null>(null);

  const saveLocation = useCallback(
    async (
      changes: { identity?: LocationIdentity; profile?: LocationProfile },
      rev: number,
    ) => {
      setConflict(null);
      try {
        let patch: Partial<LocationRecord> = {};
        let at = rev;

        if (changes.identity) {
          patch = await patchLocation(locationId, { rev: at, ...changes.identity });
          at = patch.rev ?? at;
        }
        if (changes.profile) {
          patch = { ...patch, ...(await setLocationProfile(locationId, changes.profile, at)) };
        }

        location.setData((current) => (current ? { ...current, ...patch } : current));
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) setConflict(err.message);
        throw err;
      }
    },
    [location, locationId],
  );

  if (location.loading) return <PageLoading label="Loading location" />;

  if (location.error || !location.data) {
    return (
      <LoadError
        what="this location"
        message={location.error ?? "It may have been deleted."}
        onRetry={location.reload}
        escape={{ label: "Back to home", onClick: () => navigate("/") }}
      />
    );
  }

  const record = location.data;

  return (
    <Tabs.Root value={tab} defaultValue="profile" onValueChange={setTab}>
      <PageBar
        crumbs={[{ label: "Locations", to: LOCATIONS_PATH }]}
        title={record.name}
        menu={[copyLink, {
              label: "Delete",
              icon: <TrashIcon className="size-4 shrink-0 fill-none stroke-current stroke-[1.5]" />,
              danger: true,
              onSelect: () => setDeleteOpen(true),
            }]}
        tabs={
          <Tabs.List className="overflow-x-auto border-b border-line">
            <Tabs.Tab value="profile">Profile</Tabs.Tab>
            <Tabs.Tab value="files">Files</Tabs.Tab>
          </Tabs.List>
        }
      />

      <ConfirmDestroyDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        label="Delete"
        title={`Delete ${record.name}?`}
        summary={
          "The location, its profile and its whole reference library go. " +
          "Runs shot in it stay — a run really was shot here, and " +
          "deleting the location is not a reason to delete the work."
        }
        confirmWord={record.name}
        onConfirm={async () => {
          await deleteLocation(record.id, "delete", true);
          navigate(LOCATIONS_PATH);
        }}
      />

      <Tabs.Panel value="profile">
        <ProfileForm
          key={record.rev}
          identity={{ name: record.name }}
          profile={record.profile}
          rev={record.rev}
          onSave={saveLocation}
          conflict={conflict}
          onReload={location.reload}
          template={template.data}
          schema={LOCATION_SCHEMA}
        />
      </Tabs.Panel>

      <Tabs.Panel value="files">
        <FolderTab rootId={record.root} label={record.name} />
      </Tabs.Panel>
    </Tabs.Root>
  );
}
