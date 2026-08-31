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

  // **Above the early returns, and that is not style.** These are hooks, and
  // React requires the same hooks in the same order on every render — with
  // `if (rootTree.loading) return` between them and the top, the first
  // resolved render ran three hooks the loading render had not, which React
  // reports as a changed hook order and which corrupts state silently in
  // production.
  const previews = useMemo(
    () => Object.fromEntries((result?.preview ?? []).map((p) => [p.angle, p])),
    [result],
  );
  const drafts = useMemo(
    () => Object.fromEntries((result?.drafted ?? []).map((d) => [d.angle, d])),
    [result],
  );
  const problems = useMemo(
    () => Object.fromEntries((result?.failed ?? []).map((f) => [f.angle, f.error])),
    [result],
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

  // The angle the pool on the right is picking for. Defaults to the first, so
  // the panel is never a dead box asking you to choose before you can start.
  const focused = angles.find((a) => a.id === openAngle) ?? angles[0];


  return (
    <div className="flex flex-col gap-4">
      <Card.Root>
        <Card.Title>Where the runs go</Card.Title>
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
          <div className="flex flex-col justify-end gap-1">
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
          </div>
        </div>
      </Card.Root>

      {failed ? (
        <Alert.Root intent="danger">
          <Alert.Title>The turnaround was refused</Alert.Title>
          <Alert.Description>{failed}</Alert.Description>
        </Alert.Root>
      ) : null}

      {spec.loading || pool.loading ? <Spinner /> : null}

      {/*
        **Two columns where there is room for two.** The angles are the work and
        the pool is the tool, so the pool goes to the side and STAYS there —
        `sticky`, because picking for the eleventh angle otherwise means
        scrolling the grid back into view for every one of them. Below `lg` it
        stacks, which is the same two things in the only order that fits.
      */}
      <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(300px,400px)] lg:items-start">
        <div className="flex flex-col gap-4">
          {angles.map((angle) => (
            <AngleCard
              key={angle.id}
              angle={angle}
              files={pool.data?.items ?? []}
              picked={picked[angle.id] ?? []}
              focused={focused?.id === angle.id}
              onFocus={() => setOpenAngle(angle.id)}
              onCopyToAll={() => copyToAll(angle.id)}
              preview={previews[angle.id]?.plan.prompt}
              draft={drafts[angle.id]}
              problem={problems[angle.id]}
              project={project}
            />
          ))}
        </div>

        <aside className="lg:sticky lg:top-4">
          <Card.Root>
            <Card.Title>
              {focused ? `Photographs for ${focused.id}` : "Pick an angle"}
            </Card.Title>
            {focused ? (
              <>
                <Text tone="muted">
                  Click in the order the model should see them — a prompt citing
                  [Image2] means the second one.
                </Text>
                <div className="grid grid-cols-3 gap-2">
                  {(pool.data?.items ?? []).map((file) => {
                    const at = (picked[focused.id] ?? []).indexOf(file.id);
                    return (
                      <button
                        key={file.id}
                        type="button"
                        onClick={() => toggle(focused.id, file.id)}
                        aria-pressed={at >= 0}
                        aria-label={`${focused.id}: ${file.name}${at >= 0 ? `, picked ${at + 1}` : ""}`}
                        className="relative text-left"
                      >
                        <MediaThumb
                          nodeId={file.id}
                          url={file.url}
                          name={file.name}
                          dimmed={(picked[focused.id] ?? []).length > 0 && at < 0}
                          badge={at >= 0 ? String(at + 1) : undefined}
                        />
                      </button>
                    );
                  })}
                </div>
              </>
            ) : (
              <Text tone="muted">
                Choose an angle on the left to pick its photographs.
              </Text>
            )}
          </Card.Root>
        </aside>
      </div>
    </div>
  );
}

//: The blank bible template's own placeholder marker. A prompt still holding
//: one is a prompt asking a model to render the words `<garment>`.
const UNFILLED = /<[a-z][^<>]{2,60}>/g;

/**
 * One angle: what it is, what it will be shot from, and what it would say.
 *
 * The plate is the point of the header. An angle id says
 * `face_three_quarter_back_right` and its prompt spends a paragraph defining
 * that in terms of what is visible in frame; the picture says it at a glance.
 * These are the plates a face angle stopped SENDING when the guide was found to
 * distort the face it existed to record — which is exactly why showing them is
 * free: an illustration outside the payload cannot influence a render.
 *
 * **The picks are shown large.** They were 48px, which is not a size anybody can
 * judge a photograph at — and judging them is the entire decision this screen
 * exists for.
 *
 * **The preview belongs here, not in a list at the bottom.** What an angle will
 * say is a fact about that angle, and reading it meant scrolling past fourteen
 * cards to a stack of prose in a different order.
 */
function AngleCard({
  angle,
  files,
  picked,
  focused,
  onFocus,
  onCopyToAll,
  preview,
  draft,
  problem,
  project,
}: {
  angle: SpecAngle;
  files: FileEntry[];
  picked: string[];
  focused: boolean;
  onFocus: () => void;
  onCopyToAll: () => void;
  preview?: string;
  draft?: { angle: string; id: string; status: string };
  problem?: string;
  project: string;
}) {
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
    <Card.Root
      // The focused angle is the one the pool on the right is picking for, so
      // it has to be visible at a glance — otherwise every click lands
      // somewhere the eye is not.
      className={focused ? "outline outline-2 outline-primary" : undefined}
    >
      <div className="flex items-start gap-3">
        {plate.data ? (
          <span className="w-20 shrink-0">
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
        {chosen.map((file, at) => (
          <span key={file.id} className="w-28">
            <MediaThumb
              nodeId={file.id}
              url={file.url}
              name={file.name}
              badge={String(at + 1)}
              showName
            />
          </span>
        ))}
        {chosen.length === 0 ? <Text tone="muted">No photographs yet.</Text> : null}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button intent="ghost" onClick={onFocus} aria-pressed={focused}>
          {chosen.length ? "Change" : "Pick photographs"}
        </Button>
        {chosen.length > 0 ? (
          <Button intent="ghost" onClick={onCopyToAll}>
            Use for every angle
          </Button>
        ) : null}
        {draft ? (
          <Link to={runPath(project, draft.id)}>Open the draft</Link>
        ) : null}
      </div>

      {problem ? (
        <Alert.Root intent="warning">
          <Alert.Title>Not drafted</Alert.Title>
          <Alert.Description>{problem}</Alert.Description>
        </Alert.Root>
      ) : null}

      {preview && UNFILLED.test(preview) ? (
        <Alert.Root intent="warning">
          <Alert.Title>This character's bible is not filled in</Alert.Title>
          <Alert.Description>
            {/*
              The blank bible template writes its own placeholders — `<garment>`,
              `<one plain colour, optional>` — and `top_text` reads them out
              verbatim, so they reach the prompt as literal angle brackets and a
              model is asked to render a `<garment>`. Nothing said so: the
              preview showed them beside real prose and left it to be noticed.

              Matched on the template's own marker rather than a list of known
              placeholders, so a field nobody has thought of is caught too.
            */}
            {preview.match(UNFILLED)?.join(", ")} — these come from the bible,
            not from the angle. Fill them in on the Profile tab under Wardrobe
            before shooting, or the model is asked to render them literally.
          </Alert.Description>
        </Alert.Root>
      ) : null}

      {preview ? (
        <>
          <Text variant="caption" tone="muted">
            What this angle would say
          </Text>
          {/* `whitespace-pre-wrap`: HTML collapses runs of whitespace and the
              blank lines here are real — they survive assembly and reach the
              model. */}
          <Text className="whitespace-pre-wrap font-mono">{preview}</Text>
        </>
      ) : null}
    </Card.Root>
  );
}
