import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Alert, Badge, Button, Card, Select, Spinner, Text } from "@ansavva/design-system";

import {
  draftTurnaround,
  getProjects,
  getReel,
  getAsset,
  getReferenceSpec,
  getTree,
  resolvePath,
} from "../../apis/studio";
import { MediaThumb } from "../media/MediaThumb";
import { useResource } from "../../hooks/useResource";
import type { CharacterRecord, FileEntry, SpecAngle, TurnaroundResult } from "../../types";
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
 * **And the choice is per ANGLE.** A profile angle wants the profile
 * photographs; a front angle does not; a body angle wants the figure shots a
 * head-and-shoulders pool barely has. One selection for all fourteen made the
 * commonest correction — this angle needs different pictures — impossible to
 * express, so it is fourteen selections. `Use for every angle` copies one
 * across when they genuinely are the same, which is a bulk edit rather than a
 * default: every angle still ends up holding its own explicit list.
 *
 * ## The plate says what the angle is
 *
 * Each angle shows its `illustration` — the generic figure from `config/`. It
 * is what the orientation MEANS, in a picture, next to the words asking for it.
 * These are the same plates a face angle stopped sending to the model, which is
 * exactly why they are safe to show: an illustration that is not in the payload
 * cannot influence a render.
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
  //: angle id -> the node ids picked for it, IN PICK ORDER.
  const [picked, setPicked] = useState<Record<string, string[]>>({});
  const [openAngle, setOpenAngle] = useState<string | null>(null);
  const [result, setResult] = useState<TurnaroundResult | null>(null);
  const [busy, setBusy] = useState<"preview" | "draft" | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const projects = useResource(["projects"], useCallback(() => getProjects(), []));
  const spec = useResource(["reference-spec"], useCallback(() => getReferenceSpec(), []));

  const angles = useMemo(
    () => (spec.data?.angles ?? []).filter((a) => group === "all" || a.group === group),
    [group, spec.data],
  );

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

  const toggle = useCallback((angleId: string, node: string) => {
    setResult(null);
    setPicked((current) => {
      const held = current[angleId] ?? [];
      return {
        ...current,
        [angleId]: held.includes(node)
          ? held.filter((n) => n !== node)
          : [...held, node],
      };
    });
  }, []);

  // A bulk EDIT, not a default: it writes the same explicit list onto every
  // angle, and each one can then be changed. A default would have been a thing
  // angles inherit, which is the shape that made "this angle needs different
  // pictures" impossible to say.
  const copyToAll = useCallback(
    (from: string) =>
      setPicked((current) => {
        const source = current[from] ?? [];
        return Object.fromEntries(angles.map((a) => [a.id, [...source]]));
      }),
    [angles],
  );

  const send = useCallback(
    async (preview: boolean) => {
      setBusy(preview ? "preview" : "draft");
      setFailed(null);
      try {
        setResult(
          await draftTurnaround(record.id, {
            project,
            // Per angle, and nothing else. There is no fallback from here: the
            // route takes `identity` as one, and sending both would let an
            // angle nobody picked for shoot anyway.
            identity: [],
            identity_by_angle: Object.fromEntries(
              angles.map((a) => [a.id, picked[a.id] ?? []]),
            ),
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
    // `angles` belongs here: it is what decides WHICH angles get sent, and a
    // stale copy would draft the previous group's list after the filter moved.
    [angles, group, picked, project, record.id],
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

  // Every angle, not any angle. A shoot that half-happens because the twelfth
  // was the one nobody picked for is the failure this guards — the route
  // refuses it too, and refusing here means it is visible before the click
  // rather than as an error after it.
  const unpicked = angles.filter((a) => (picked[a.id] ?? []).length === 0);
  const ready = project !== "" && angles.length > 0 && unpicked.length === 0;

  return (
    <div className="flex flex-col gap-4">
      <Card.Root>
        <Card.Title>Where the runs go</Card.Title>
        <div className="flex flex-col gap-2">
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
        </div>
      </Card.Root>

      {(spec.loading || pool.loading) ? <Spinner /> : null}

      {angles.map((angle) => (
        <AnglePicker
          key={angle.id}
          angle={angle}
          files={pool.data?.items ?? []}
          picked={picked[angle.id] ?? []}
          open={openAngle === angle.id}
          onOpen={() => setOpenAngle(openAngle === angle.id ? null : angle.id)}
          onToggle={(node) => toggle(angle.id, node)}
          onCopyToAll={() => copyToAll(angle.id)}
        />
      ))}

      <Card.Root>
        <div className="flex flex-wrap items-center gap-3">
          <Button intent="ghost" onClick={() => send(true)} disabled={!ready || busy !== null}>
            {busy === "preview" ? "Assembling…" : "Preview"}
          </Button>
          <Button onClick={() => send(false)} disabled={!ready || busy !== null}>
            {busy === "draft" ? "Drafting…" : `Draft ${angles.length} angle(s)`}
          </Button>
          <Text tone="muted">
            {unpicked.length > 0
              ? `${unpicked.length} angle(s) still need photographs.`
              : "Nothing is approved and nothing bills."}
          </Text>
        </div>
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
              <div className="flex flex-col gap-2">
                {/* `whitespace-pre-wrap`, because HTML collapses runs of
                    whitespace and the blank lines in a prompt are now real —
                    they survive assembly and reach the model. Rendered without
                    it, a paragraphed prompt reads as the same wall of text it
                    was written to stop being, and the editor would look like it
                    had done nothing. */}
                <Text className="whitespace-pre-wrap font-mono">{entry.plan.prompt}</Text>
              </div>
            </Card.Root>
          ))
        : null}

      {result.drafted ? (
        <Card.Root>
          <Card.Title>{result.drafted.length} draft(s)</Card.Title>
          <div className="flex flex-col gap-2">
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
          </div>
        </Card.Root>
      ) : null}
    </>
  );
}


/**
 * One angle: what it is, and which photographs it will be shot from.
 *
 * The plate is the point of the header. An angle id says `face_three_quarter_back_right`
 * and the prompt spends a paragraph defining it in terms of what is visible in
 * frame; the picture says it at a glance. These plates are the ones a face
 * angle stopped SENDING when the guide was found to distort the face it existed
 * to record — which is exactly why showing them is free: an illustration
 * outside the payload cannot influence a render.
 */
function AnglePicker({
  angle,
  files,
  picked,
  open,
  onOpen,
  onToggle,
  onCopyToAll,
}: {
  angle: SpecAngle;
  files: FileEntry[];
  picked: string[];
  open: boolean;
  onOpen: () => void;
  onToggle: (node: string) => void;
  onCopyToAll: () => void;
}) {
  // Resolve the path, then SIGN it. Two calls, and the second is not optional:
  // `/api/resolve` answers a node view with no url, and `MediaThumb` only
  // re-signs from its `onError` — which an empty `src` never fires, because the
  // browser does not attempt a load at all. Fourteen empty boxes and no network
  // request is what that looked like.
  const plate = useResource(
    angle.illustration ? ["plate", angle.illustration] : null,
    angle.illustration
      ? async () => {
          const node = await resolvePath(angle.illustration as string);
          return { id: node.id, url: (await getAsset(node.id)).url };
        }
      : null,
  );
  const chosen = useMemo(
    () => picked.map((id) => files.find((f) => f.id === id)).filter(Boolean) as FileEntry[],
    [files, picked],
  );

  return (
    <Card.Root>
      <div className="flex items-start gap-3">
        {plate.data ? (
          <span className="w-16 shrink-0">
            <MediaThumb
              nodeId={plate.data.id}
              url={plate.data.url}
              name={angle.id}
              aspect="square"
              fit="contain"
            />
          </span>
        ) : null}
        <span className="flex min-w-0 flex-col gap-1">
          <Text>
            {angle.id} <Badge size="sm">{angle.group}</Badge>
          </Text>
          <Text tone="muted">{angle.description}</Text>
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {/* The picks themselves, always visible — the answer to "what will this
            angle be shot from" should not need a click. */}
        {chosen.map((file, at) => (
          <span key={file.id} className="w-12">
            <MediaThumb
              nodeId={file.id}
              url={file.url}
              name={file.name}
              badge={String(at + 1)}
            />
          </span>
        ))}
        {chosen.length === 0 ? <Text tone="muted">No photographs yet.</Text> : null}
        <Button intent="ghost" onClick={onOpen} aria-expanded={open}>
          {open ? "Done" : chosen.length ? "Change" : "Pick photographs"}
        </Button>
        {chosen.length > 0 ? (
          <Button intent="ghost" onClick={onCopyToAll}>
            Use for every angle
          </Button>
        ) : null}
      </div>

      {open ? (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          {files.map((file) => {
            const at = picked.indexOf(file.id);
            return (
              <button
                key={file.id}
                type="button"
                onClick={() => onToggle(file.id)}
                aria-pressed={at >= 0}
                aria-label={`${angle.id}: ${file.name}${at >= 0 ? `, picked ${at + 1}` : ""}`}
                className="relative text-left"
              >
                <MediaThumb
                  nodeId={file.id}
                  url={file.url}
                  name={file.name}
                  dimmed={picked.length > 0 && at < 0}
                  badge={at >= 0 ? String(at + 1) : undefined}
                />
              </button>
            );
          })}
        </div>
      ) : null}
    </Card.Root>
  );
}
