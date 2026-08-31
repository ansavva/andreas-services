import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Alert, Badge, Button, Card, Select, Spinner, Text } from "@ansavva/design-system";

import { draftTurnaround, getProjects, getReel, getTree } from "../../apis/studio";
import { MediaThumb } from "../media/MediaThumb";
import { useResource } from "../../hooks/useResource";
import type { CharacterRecord, TurnaroundResult } from "../../types";
import { runPath } from "../../utils/location";

/**
 * Shoot a character's reference set — the standard angles — from the app.
 *
 * **This is the half that made the rest of it worth doing.** The prompts became
 * rows the API assembles and this screen edits (`/reference-spec`), but starting
 * a reference render still meant a terminal, so a person could tune the words
 * and then not be able to use them. `POST /api/characters/<id>/turnaround` does
 * the assembly and the drafting; everything here is the one decision it
 * deliberately refuses to make.
 *
 * ## Choosing the photographs is the whole screen
 *
 * The route will not guess which images carry identity, and that is not
 * squeamishness about defaults: which photographs say who somebody is is the
 * judgement a reference library is built out of, and a seed pool sorted by name
 * opens with whatever was uploaded first. The CLI refuses an oversized pool
 * rather than truncating it (`_too_many`), and this is that refusal's positive
 * form — a grid of the actual pictures, chosen by eye.
 *
 * **Order is part of the choice.** The images go to the model in the order they
 * are picked, and a prompt citing `[Image2]` means the second one in that list,
 * so each selection carries its number rather than a tick.
 *
 * ## Nothing here spends
 *
 * Preview assembles and records nothing. Draft writes one unapproved `draft` per
 * angle — `NEVER_BILLED` names that state — and approving and sending remain
 * separate, on the run's own page. Hard rule #2 is exactly where it was: this
 * makes the payload, a person still says yes to it.
 */
export function TurnaroundPanel({ record }: { record: CharacterRecord }) {
  const [project, setProject] = useState("");
  const [group, setGroup] = useState("all");
  const [picked, setPicked] = useState<string[]>([]);
  const [result, setResult] = useState<TurnaroundResult | null>(null);
  const [busy, setBusy] = useState<"preview" | "draft" | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const projects = useResource(["projects"], useCallback(() => getProjects(), []));

  // The character's own folders, to find `seed/`. Its node id is not on the
  // record — the four pools are convention rather than schema, so a character
  // may not have one, and the panel says so instead of assuming.
  const rootTree = useResource(
    ["tree", record.root],
    useCallback(() => getTree({ node: record.root }, "name"), [record.root]),
  );
  const seedFolder = useMemo(
    () => (rootTree.data?.folders ?? []).find((f) => f.name === "seed"),
    [rootTree.data],
  );

  // `getReel`, not `getTree`: a seed pool is a TREE the moment anyone files it
  // — `original/`, `restored/`, a folder per age — and a listing one level deep
  // shows only what was never filed. That exact blindness kept thirteen
  // restored photographs out of a shoot's view on the CLI side.
  const pool = useResource(
    seedFolder ? ["reel", seedFolder.id] : null,
    seedFolder ? () => getReel({ node: seedFolder.id }, "name") : null,
  );

  const toggle = useCallback((id: string) => {
    setResult(null);
    setPicked((current) =>
      current.includes(id) ? current.filter((n) => n !== id) : [...current, id],
    );
  }, []);

  const send = useCallback(
    async (preview: boolean) => {
      setBusy(preview ? "preview" : "draft");
      setFailed(null);
      try {
        setResult(
          await draftTurnaround(record.id, {
            project,
            identity: picked,
            group: group === "all" ? undefined : (group as "face" | "body"),
            preview,
          }),
        );
      } catch (problem) {
        setFailed(problem instanceof Error ? problem.message : String(problem));
      } finally {
        setBusy(null);
      }
    },
    [group, picked, project, record.id],
  );

  if (rootTree.loading) return <Spinner />;
  if (!seedFolder) {
    return (
      <Alert.Root intent="info">
        <Alert.Title>This character has no seed pool</Alert.Title>
        <Alert.Description>
          A turnaround is driven from the founding photographs. Add some before
          shooting: driving one off already-generated references feeds model
          output back in as identity and compounds drift.
        </Alert.Description>
      </Alert.Root>
    );
  }

  const ready = project !== "" && picked.length > 0;

  return (
    <div className="flex flex-col gap-4">
      <Card.Root>
        <Card.Title>Where the runs go</Card.Title>
        <Card.Body>
          <div className="flex flex-wrap gap-4">
            <div className="flex flex-col gap-1">
              <Text variant="caption" tone="muted">
                Project
              </Text>
              {/* Required and never inferred: a run belongs to a project, and
                  guessing puts runs somewhere nobody looks again. */}
              <Select
                aria-label="Project"
                options={[
                  { value: "", label: "Choose a project…" },
                  ...(projects.data ?? []).map((p) => ({ value: p.id, label: p.slug })),
                ]}
                value={project}
                onValueChange={setProject}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Text variant="caption" tone="muted">
                Angles
              </Text>
              <Select
                aria-label="Angles"
                options={[
                  { value: "all", label: "Face and body" },
                  { value: "face", label: "Face only" },
                  { value: "body", label: "Body only" },
                ]}
                value={group}
                onValueChange={setGroup}
              />
            </div>
          </div>
        </Card.Body>
      </Card.Root>

      <Card.Root>
        <Card.Title>Which photographs say who this is</Card.Title>
        <Card.Body>
          <Text tone="muted">
            Picked in order — the model is handed them in this order, and a
            prompt citing [Image2] means the second one.
          </Text>
          {pool.loading ? <Spinner /> : null}
          <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-5">
            {(pool.data?.items ?? []).map((file) => {
              const at = picked.indexOf(file.id);
              return (
                <button
                  key={file.id}
                  type="button"
                  onClick={() => toggle(file.id)}
                  aria-pressed={at >= 0}
                  aria-label={`${file.name}${at >= 0 ? `, picked ${at + 1}` : ""}`}
                  className="relative text-left"
                >
                  <MediaThumb
                    nodeId={file.id}
                    url={file.url}
                    name={file.name}
                    dimmed={picked.length > 0 && at < 0}
                    /* The NUMBER, not a tick. Order is part of the choice, and
                       a tick would say "chosen" while hiding which slot it
                       lands in — the thing a prompt's citations depend on. */
                    badge={at >= 0 ? String(at + 1) : undefined}
                  />
                </button>
              );
            })}
          </div>
          {!pool.loading && (pool.data?.items ?? []).length === 0 ? (
            <Text tone="muted">This seed pool holds no images.</Text>
          ) : null}
        </Card.Body>
        <Card.Footer>
          <Button intent="ghost" onClick={() => send(true)} disabled={!ready || busy !== null}>
            {busy === "preview" ? "Assembling…" : "Preview"}
          </Button>
          <Button onClick={() => send(false)} disabled={!ready || busy !== null}>
            {busy === "draft" ? "Drafting…" : "Draft the angles"}
          </Button>
          <Text tone="muted">
            {picked.length === 0
              ? "Pick at least one photograph."
              : `${picked.length} picked. Nothing is approved and nothing bills.`}
          </Text>
        </Card.Footer>
      </Card.Root>

      {failed ? (
        <Alert.Root intent="danger">
          <Alert.Title>The turnaround was refused</Alert.Title>
          <Alert.Description>{failed}</Alert.Description>
        </Alert.Root>
      ) : null}

      {result ? <Outcome result={result} project={project} /> : null}
    </div>
  );
}

function Outcome({ result, project }: { result: TurnaroundResult; project: string }) {
  return (
    <>
      {(result.failed ?? []).length > 0 ? (
        <Alert.Root intent="warning">
          <Alert.Title>
            {result.failed.length} angle(s) were not drafted
          </Alert.Title>
          <Alert.Description>
            {/* One bad angle does not cancel the rest — a failure is almost
                always a property of that angle alone, most often a template
                citing a block somebody deleted. */}
            {result.failed.map((f) => `${f.angle}: ${f.error}`).join(" · ")}
          </Alert.Description>
        </Alert.Root>
      ) : null}

      {result.preview
        ? result.preview.map((entry) => (
            <Card.Root key={entry.angle}>
              <Card.Title>
                {entry.angle} <Badge size="sm">preview</Badge>
              </Card.Title>
              <Card.Body>
                <Text>{entry.plan.prompt}</Text>
              </Card.Body>
            </Card.Root>
          ))
        : null}

      {result.drafted ? (
        <Card.Root>
          <Card.Title>{result.drafted.length} draft(s)</Card.Title>
          <Card.Body>
            <Text tone="muted">
              Nothing is approved and nothing has been submitted. Open each one
              to read its payload and say yes to it.
            </Text>
            <ul className="mt-2 flex flex-col gap-1">
              {result.drafted.map((entry) => (
                <li key={entry.id}>
                  <Link to={runPath(project, entry.id)}>{entry.angle}</Link>
                </li>
              ))}
            </ul>
          </Card.Body>
        </Card.Root>
      ) : null}
    </>
  );
}
