import { useCallback, useEffect, useMemo, useState } from "react";
import type { KeyboardEvent, MouseEvent } from "react";
import { Link } from "react-router-dom";

import {
  Alert,
  Badge,
  Button,
  Card,
  Select,
  Text,
  Tooltip,
  buttonClass,
} from "@ansavva/design-system";

import {
  draftTurnaround,
  getProjects,
  getProject,
  getReel,
  getReferenceSpec,
  getTree,
} from "../../apis/studio";
import { ApertureSpinner } from "../common/Aperture";
import { AnglePlate } from "../common/AnglePlate";
import { PreviewBox } from "../common/PromptPreview";
import { Marked, unfilledIn } from "../common/UnfilledMarks";
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
  /**
   * **The angle shot first, and the render everything else chains off.**
   *
   * A turnaround is not N independent shoots. Every hand-authored production
   * set was made as one anchor and then the rest chained off it, each binding
   * the anchor's output as `[Image1]` and each told to take the wardrobe and
   * the background from it. Shot independently, the same fourteen prompts
   * produced fourteen different shirts.
   *
   * Two pieces of state because they are two decisions separated by a
   * generation: which angle leads, and — once it has been approved, submitted
   * and looked at — which of its images is good enough to hold the set to.
   * Nothing here picks the second for you; that is the same judgement the
   * photographs themselves get.
   */
  const [anchorAngle, setAnchorAngle] = useState<string | null>(null);
  const [anchorNode, setAnchorNode] = useState<string | null>(null);
  const [result, setResult] = useState<TurnaroundResult | null>(null);
  const [busy, setBusy] = useState<"draft" | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  //: angle id -> the assembled prompt, kept current without being asked for.
  const [assembled, setAssembled] = useState<Record<string, string>>({});

  const projects = useResource(["projects"], useCallback(() => getProjects(), []));
  // The project's folder, so the anchor can be chosen from what this shoot has
  // already produced. A project summary carries no root, so this is a second
  // read rather than something the listing could have answered.
  const projectRecord = useResource(
    project ? ["project", project] : null,
    project ? () => getProject(project) : null,
  );
  const projectMedia = useResource(
    projectRecord.data ? ["reel", projectRecord.data.root] : null,
    projectRecord.data
      ? () => getReel({ node: projectRecord.data!.root }, "newest")
      : null,
  );
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

  /**
   * A modified click opens the photograph itself, rather than picking it.
   *
   * These are thumbnails of the only pictures that will say who this person is,
   * and the decision is made by eye — so being able to look at one properly,
   * without leaving the screen you are choosing on, is part of the job. Cmd or
   * Ctrl is the gesture a browser already trained everyone to expect from a
   * thing that opens in a new tab.
   *
   * Opened synchronously off the click with the url the listing already
   * carries: re-signing first would put an `await` between the gesture and the
   * `window.open`, which is exactly what a popup blocker stops.
   */
  const opened = useCallback((event: MouseEvent, url: string) => {
    if (!event.metaKey && !event.ctrlKey) return false;
    event.preventDefault();
    window.open(url, "_blank", "noopener,noreferrer");
    return true;
  }, []);

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

  const selection = useMemo(
    () => Object.fromEntries(angles.map((a) => [a.id, picked[a.id] ?? []])),
    [angles, picked],
  );

  /**
   * The angles this press is about.
   *
   * **Phase one is the anchor alone.** Drafting all fourteen and shooting the
   * anchor out of that pile would leave thirteen payloads written against a
   * render that does not exist yet — and a payload is what a person approves,
   * so it has to be assembled after the thing it cites.
   */
  const shooting = useMemo(() => {
    if (anchorAngle && !anchorNode) return angles.filter((a) => a.id === anchorAngle);
    if (anchorAngle) return angles.filter((a) => a.id !== anchorAngle);
    return angles;
  }, [anchorAngle, anchorNode, angles]);

  const draft = useCallback(async () => {
    setBusy("draft");
    setFailed(null);
    try {
      setResult(
        await draftTurnaround(record.id, {
          project,
          angles: shooting.map((a) => a.id),
          ...(anchorNode ? { anchor: anchorNode } : {}),
          // Per angle, and nothing else. There is no fallback from here: the
          // route takes `identity` as one, and sending both would let an
          // angle nobody picked for shoot anyway.
          identity: [],
          identity_by_angle: selection,
          group: group === "all" ? undefined : (group as "face" | "body"),
        }),
      );
    } catch (problem) {
      setFailed(problem instanceof Error ? problem.message : String(problem));
    } finally {
      setBusy(null);
    }
  }, [anchorNode, group, project, record.id, selection, shooting]);

  /**
   * **The prompts assemble themselves, and there is no Preview button.**
   *
   * There was one, and it was the wrong shape twice over: what an angle would
   * say is the thing that tells you whether your choices are right, so putting
   * it behind a click meant deciding first and reading afterwards — and the
   * button was disabled until a project was chosen and all fourteen angles had
   * photographs, which is the point at which there is nothing left to decide.
   *
   * The route was built for exactly this — `_draft_one` says a preview stops
   * before the write and is safe to call on every keystroke — and its two
   * guards, a project and a full picking, are now about drafting alone.
   *
   * Debounced, because clicking through a pool of fifty photographs is a burst
   * of changes and only the last one is worth an assembly.
   */
  useEffect(() => {
    if (angles.length === 0) return;
    const timer = setTimeout(() => {
      void draftTurnaround(record.id, {
        identity: [],
        identity_by_angle: selection,
        group: group === "all" ? undefined : (group as "face" | "body"),
        // The anchor changes what every prompt SAYS, so a preview without it
        // would be a preview of a payload nobody is going to send.
        ...(anchorNode ? { anchor: anchorNode } : {}),
        preview: true,
      })
        .then((got) =>
          setAssembled(
            Object.fromEntries((got.preview ?? []).map((p) => [p.angle, p.plan.prompt])),
          ),
        )
        // A preview that fails is not an error a person did anything about, and
        // it must not take the screen: the per-angle refusal already surfaces
        // through `failed` on the response, and a network blip here would
        // otherwise replace the whole panel with a red box mid-click.
        .catch(() => undefined);
    }, 250);
    return () => clearTimeout(timer);
  }, [anchorNode, angles.length, group, record.id, selection]);

  // **Above the early returns, and that is not style.** These are hooks, and
  // React requires the same hooks in the same order on every render — with
  // `if (rootTree.loading) return` between them and the top, the first
  // resolved render ran three hooks the loading render had not, which React
  // reports as a changed hook order and which corrupts state silently in
  // production.
  const drafts = useMemo(
    () => Object.fromEntries((result?.drafted ?? []).map((d) => [d.angle, d])),
    [result],
  );
  const problems = useMemo(
    () => Object.fromEntries((result?.failed ?? []).map((f) => [f.angle, f.error])),
    [result],
  );

  if (rootTree.loading) return <ApertureSpinner />;
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
  // An anchored pass carries its identity in the anchor, so it needs no fresh
  // picks — requiring them would make the chained phase impossible to express.
  const unpicked = anchorNode
    ? []
    : shooting.filter((a) => (picked[a.id] ?? []).length === 0);
  const ready = project !== "" && shooting.length > 0 && unpicked.length === 0;

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
              <Button onClick={draft} disabled={!ready || busy !== null}>
                {busy === "draft"
                  ? "Drafting…"
                  : anchorAngle && !anchorNode
                    ? "Draft the anchor"
                    : `Draft ${shooting.length} angle(s)`}
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

      {spec.loading || pool.loading ? <ApertureSpinner /> : null}

      {/*
        **The anchor, and it is the whole shape of a turnaround.**

        Every hand-authored production set was one angle shot first and the rest
        chained off its render — each binding it as `[Image1]`, each told to take
        the wardrobe and the background from it. Shot independently the same
        prompts produced a different shirt every time, because nothing in them
        held it.

        Two steps, deliberately, and the second is a person looking at a
        picture: which angle leads, then which of its images is good enough to
        hold the set to. Nothing here picks the second automatically — the
        anchor decides what thirteen more renders will look like, which is a
        heavier judgement than any of them individually.
      */}
      <Card.Root>
        <Card.Title>Chain off an anchor</Card.Title>
        {anchorAngle === null ? (
          <Text tone="muted">
            Mark one angle as the anchor to shoot it first. The rest then chain
            off its render and take their wardrobe and background from it.
          </Text>
        ) : (
          <div className="flex flex-col gap-2">
            <Text tone="muted">
              <strong>{anchorAngle}</strong> leads.{" "}
              {anchorNode
                ? `The remaining ${shooting.length} angle(s) will bind the chosen render as [Image1].`
                : "Draft and shoot it, then pick its render below to unlock the rest."}
            </Text>
            {projectMedia.data && projectMedia.data.items.length > 0 ? (
              <div className="grid grid-cols-[repeat(auto-fill,minmax(130px,1fr))] gap-2">
                {projectMedia.data.items.map((file) => (
                  <button
                    key={file.id}
                    type="button"
                    onClick={(event) => {
                      if (opened(event, file.url)) return;
                      setAnchorNode(anchorNode === file.id ? null : file.id);
                    }}
                    aria-pressed={anchorNode === file.id}
                    aria-label={`Anchor: ${file.name}`}
                    className="relative text-left"
                  >
                    <MediaThumb
                      nodeId={file.id}
                      url={file.url}
                      name={file.name}
                      aspect="portrait"
                      fit="contain"
                      dimmed={anchorNode !== null && anchorNode !== file.id}
                      badge={anchorNode === file.id ? "1" : undefined}
                    />
                  </button>
                ))}
              </div>
            ) : (
              <Text tone="muted">
                {project === ""
                  ? "Choose a project to see what it has already produced."
                  : "Nothing rendered in this project yet."}
              </Text>
            )}
            <div>
              <Button
                intent="ghost"
                onClick={() => {
                  setAnchorAngle(null);
                  setAnchorNode(null);
                }}
              >
                Shoot every angle independently instead
              </Button>
            </div>
          </div>
        )}
      </Card.Root>

      {/*
        **An even split, because both halves are the work.** The pool was a
        400px rail showing three thumbnails across, which is not a size anybody
        picks photographs at — and picking them is the entire decision this
        screen exists for. It gets half the screen and fills it with as many
        columns as fit.

        Still `sticky`, and now scrolling in place: picking for the eleventh
        angle otherwise means scrolling the grid back into view for every one of
        them. Below `lg` it stacks, which is the same two things in the only
        order that fits.
      */}
      <div className="flex flex-col gap-4 lg:grid lg:grid-cols-2 lg:items-start">
        <div className="flex flex-col gap-4">
          {angles.map((angle) => (
            <AngleCard
              key={angle.id}
              angle={angle}
              files={pool.data?.items ?? []}
              picked={picked[angle.id] ?? []}
              focused={focused?.id === angle.id}
              onFocus={() => setOpenAngle(angle.id)}
              onRemove={(node) => toggle(angle.id, node)}
              onOpen={opened}
              anchor={anchorAngle === angle.id}
              onAnchor={() => {
                setAnchorNode(null);
                setAnchorAngle(anchorAngle === angle.id ? null : angle.id);
              }}
              onCopyToAll={() => copyToAll(angle.id)}
              preview={assembled[angle.id]}
              draft={drafts[angle.id]}
              problem={problems[angle.id]}
              project={project}
            />
          ))}
        </div>

        <aside className="lg:sticky lg:top-4 lg:max-h-[calc(100vh-6rem)] lg:overflow-auto">
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
                {/* `auto-fill`, not a column count: the panel is half the
                    screen now, and how many photographs fit across it is a
                    property of the screen rather than a number to pick. */}
                <div className="grid grid-cols-[repeat(auto-fill,minmax(130px,1fr))] gap-2">
                  {(pool.data?.items ?? []).map((file) => {
                    const at = (picked[focused.id] ?? []).indexOf(file.id);
                    return (
                      <button
                        key={file.id}
                        type="button"
                        onClick={(event) => {
                          if (opened(event, file.url)) return;
                          toggle(focused.id, file.id);
                        }}
                        aria-pressed={at >= 0}
                        aria-label={`${focused.id}: ${file.name}${at >= 0 ? `, picked ${at + 1}` : ""}`}
                        title="Click to pick — ⌘/Ctrl-click to open full size"
                        className="relative text-left"
                      >
                        {/*
                          **`contain`, and portrait.** The default crops to a
                          square, which took the head off a standing shot and
                          the shoulders off a close portrait — on the one grid
                          in this app whose entire purpose is judging a
                          photograph by eye. A letterboxed thumbnail wastes a
                          little space; a cropped one hides the thing being
                          chosen. Portrait because these are pictures of a
                          person, so it is the ratio that leaves least of it.
                        */}
                        <MediaThumb
                          nodeId={file.id}
                          url={file.url}
                          name={file.name}
                          aspect="portrait"
                          fit="contain"
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
  onRemove,
  onOpen,
  anchor,
  onAnchor,
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
  onRemove: (node: string) => void;
  onOpen: (event: MouseEvent, url: string) => boolean;
  /** Whether this angle leads the set — see the panel's note on the anchor. */
  anchor: boolean;
  onAnchor: () => void;
  onCopyToAll: () => void;
  preview?: string;
  draft?: { angle: string; id: string; status: string };
  problem?: string;
  project: string;
}) {
  const chosen = useMemo(
    () => picked.map((id) => files.find((f) => f.id === id)).filter(Boolean) as FileEntry[],
    [files, picked],
  );

  return (
    <Card.Root
      // **The card IS the control.** Choosing which angle the pool picks for
      // was a button inside the card saying "Pick photographs", which is a
      // second thing to aim at for a decision the card itself already stands
      // for — and it read as "open something" rather than "this one".
      role="button"
      tabIndex={0}
      aria-pressed={focused}
      aria-label={`Pick photographs for ${angle.id}`}
      onClick={onFocus}
      onKeyDown={(event: KeyboardEvent) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onFocus();
        }
      }}
      // The focused angle is the one the pool on the right is picking for, so
      // it has to be visible at a glance — otherwise every click lands
      // somewhere the eye is not.
      className={`cursor-pointer ${focused ? "outline outline-2 outline-primary" : ""}`}
    >
      <div className="flex items-start gap-3">
        <AnglePlate path={angle.illustration} name={angle.id} />
        <span className="flex min-w-0 flex-col gap-1">
          <Text>
            {angle.id} <Badge size="sm">{angle.group}</Badge>
          </Text>
          <Text tone="muted">{angle.description}</Text>
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {chosen.map((file, at) => (
          <span key={file.id} className="relative w-28">
            {/* The same gesture as in the pool: these are the pictures the
                decision is about, and they are 112px wide here. */}
            <button
              type="button"
              onClick={(event) => {
                onOpen(event, file.url);
              }}
              aria-label={`Open ${file.name} full size`}
              title="⌘/Ctrl-click to open full size"
              className="block w-full text-left"
            >
              {/* Cropped here too, and these are the ones already chosen —
                  the picture you are checking your own decision against. */}
              <MediaThumb
                nodeId={file.id}
                url={file.url}
                name={file.name}
                aspect="portrait"
                fit="contain"
                badge={String(at + 1)}
                showName
              />
            </button>
            {/*
              **Dropping one has to be possible from here.** It was only
              possible in the pool, by finding the same photograph among fifty
              and clicking it again — so the place that shows you the mistake
              was not the place you could fix it.

              `stopPropagation` because the card is itself the control that
              selects an angle, and removing a picture is not selecting.
            */}
            <button
              type="button"
              aria-label={`Remove ${file.name} from ${angle.id}`}
              onClick={(event) => {
                event.stopPropagation();
                onRemove(file.id);
              }}
              className="absolute -top-1.5 -right-1.5 flex size-5 items-center justify-center rounded-full border border-line bg-card text-xs text-ink hover:bg-surface-alt"
            >
              ×
            </button>
          </span>
        ))}
        {chosen.length === 0 ? <Text tone="muted">No photographs yet.</Text> : null}
      </div>

      {/* `stopPropagation`: the card is a control now, and a click meant for a
          button inside it must not also re-select the card underneath. */}
      <div
          className="flex flex-wrap items-center gap-2"
          onClick={(event) => event.stopPropagation()}
        >
          <Tooltip.Root>
            <Tooltip.Trigger
              className={buttonClass({
                intent: anchor ? "primary" : "secondary",
                size: "sm",
              })}
              aria-pressed={anchor}
              onClick={onAnchor}
            >
              {anchor ? "Anchor" : "Make anchor"}
            </Tooltip.Trigger>
            <Tooltip.Content>
              Shoot this angle first and chain the rest off its render — they
              bind it as [Image1] and take their wardrobe and background from
              it. Without one, every angle is shot independently and nothing
              holds the clothing constant across the set.
            </Tooltip.Content>
          </Tooltip.Root>
          {chosen.length > 0 ? (
            <Tooltip.Root>
              {/* The outline weight, not ghost: it rewrites all fourteen
                  angles, which is the largest thing this card can do and read
                  as the least. */}
              <Tooltip.Trigger
                className={buttonClass({ intent: "secondary", size: "sm" })}
                onClick={onCopyToAll}
              >
                Use for every angle
              </Tooltip.Trigger>
              <Tooltip.Content>
                Writes this angle's photographs, in this order, onto every other
                angle — replacing whatever they hold. Each can still be changed
                afterwards; it is a bulk edit, not a default they follow.
              </Tooltip.Content>
            </Tooltip.Root>
          ) : null}
          {draft ? <Link to={runPath(project, draft.id)}>Open the draft</Link> : null}
      </div>

      {problem ? (
        <Alert.Root intent="warning">
          <Alert.Title>Not drafted</Alert.Title>
          <Alert.Description>{problem}</Alert.Description>
        </Alert.Root>
      ) : null}

      {preview && unfilledIn(preview).length > 0 ? (
        <Alert.Root intent="warning">
          <Alert.Title>This character's bible is not filled in</Alert.Title>
          <Alert.Description>
            {/* The reasoning, and the regex, are in `UnfilledMarks`. The
                prompt below marks each one where it sits; this says what to do
                about them. */}
            {unfilledIn(preview).join(", ")} — these come from the bible,
            not from the angle. Fill them in on the Profile tab under Wardrobe
            before shooting, or the model is asked to render them literally.
          </Alert.Description>
        </Alert.Root>
      ) : null}

      {preview ? (
        // The same box the reference spec shows a prompt in — it is the same
        // object one stage further on, with this character's values filled in.
        // It was a bare paragraph here and a bordered box there.
        <PreviewBox
          name={`assembled-${angle.id}`}
          label="What this angle would say"
          description="Assembled from the reference spec and this character's bible. Nothing is sent."
          ariaLabel={`Assembled prompt for ${angle.id}`}
        >
          <Marked text={preview} />
        </PreviewBox>
      ) : null}
    </Card.Root>
  );
}
