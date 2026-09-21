import { useCallback, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { Alert, Button, Dialog, Field, Select, useToast } from "@ansavva/design-system";

import { getProjects, moveRun } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import type { RunFeedRow } from "../../types";
import { runPath } from "../../utils/location";
import { cancelClass } from "../common/cancelClass";

/**
 * Move one run into another project — `PATCH /api/runs/<id>` with `project`.
 *
 * **A dialog off the run's `⋯` menu, not a line in it.** The menu's lines act
 * on press; this one needs a choice made first, and a list of every project
 * does not belong in a menu that is otherwise eight verbs. The picker lists
 * every project but the one the run is in, so the one choice that would do
 * nothing is not on offer.
 *
 * **What moves and what does not is said here, once, because the API says
 * it nowhere a person reads.** The run leaves its scene, and that scene's cut
 * if it was in it — a scene belongs to a project. Its files stay where they
 * are as bytes and re-parent as records, so nothing that names an output — a
 * binding in a later run, a chain, a movie — stops working.
 *
 * On success the feed and both projects' counts are re-read, and a lightbox
 * open on this run follows it to its new address rather than going stale on
 * one the old project no longer answers for.
 */
export function MoveRunDialog({ row, onClose }: { row: RunFeedRow; onClose: () => void }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const [destination, setDestination] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The same `["projects"]` query the sidebar and the Projects page read.
  const projects = useResource(
    ["projects"],
    useCallback(() => getProjects(), []),
  );
  const options = (projects.data ?? [])
    .filter((each) => each.id !== row.project)
    .map((each) => ({
      value: each.id,
      label: each.name || "Untitled project",
    }));

  const move = useCallback(async () => {
    if (!destination) return;
    setBusy(true);
    setError(null);
    try {
      await moveRun(row.id, destination);
      const name = options.find((each) => each.value === destination)?.label;
      toast.add({
        intent: "success",
        title: "Moved the run",
        description: name ? `Now in ${name}.` : undefined,
      });
      await Promise.all([
        client.invalidateQueries({ queryKey: ["runs"] }),
        client.invalidateQueries({ queryKey: ["run", row.id] }),
        client.invalidateQueries({ queryKey: ["project", row.project] }),
        client.invalidateQueries({ queryKey: ["project", destination] }),
        client.invalidateQueries({ queryKey: ["projects"] }),
        ...(row.scene ? [client.invalidateQueries({ queryKey: ["scene", row.scene] })] : []),
      ]);
      onClose();
      if (location.pathname === runPath(row.project, row.id)) {
        navigate(runPath(destination, row.id), { replace: true });
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }, [
    client,
    destination,
    location.pathname,
    navigate,
    onClose,
    options,
    row.id,
    row.project,
    row.scene,
    toast,
  ]);

  return (
    <Dialog.Root open onOpenChange={(next: boolean) => !next && onClose()}>
      <Dialog.Backdrop />
      <Dialog.Popup className="flex w-full max-w-md flex-col gap-4 p-4">
        <Dialog.Title>Move to another project</Dialog.Title>

        <Field.Root name="project">
          <Field.Label>Project</Field.Label>
          <Select
            options={options}
            value={destination}
            onValueChange={setDestination}
            placeholder={
              projects.loading
                ? "Loading projects…"
                : options.length
                  ? "Choose a project"
                  : "No other project"
            }
            disabled={projects.loading || !options.length}
          />
          <Field.Description>
            The run and its files go with it; nothing that names an output stops working.
            {row.scene ? " It leaves its scene, and that scene's cut." : ""}
          </Field.Description>
        </Field.Root>

        {error && (
          <Alert.Root intent="danger">
            <Alert.Title>Could not move the run</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          <Dialog.Close className={cancelClass()}>Cancel</Dialog.Close>
          <Button disabled={!destination || busy} onClick={() => void move()}>
            {busy ? "Moving…" : "Move"}
          </Button>
        </div>
      </Dialog.Popup>
    </Dialog.Root>
  );
}
