import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  Alert,
  Button,
  Drawer,
  IconButton,
  Popover,
  Text,
  Toggle,
  ToggleGroup,
  useToast,
} from "@ansavva/design-system";

import {
  clearModelDefaults,
  createRun,
  deleteRun,
  expandTemplate,
  getModelDefaults,
  getModels,
  getProject,
  getProjects,
  getRuns,
  getTemplates,
  patchRunPlan,
  setModelDefaults,
  submitRun,
  type ModelDefaults,
} from "../../apis/studio";
import {
  useCreateBar,
  useCreateBarState,
  type AttachRef,
  type Attachment,
} from "../../context/CreateBarContext";
import { FINE, useMediaQuery } from "../../hooks/useMediaQuery";
import { useResource } from "../../hooks/useResource";
import { useScrolledPast } from "../../hooks/useScrolledPast";
import type { CreatedRun, RunSummary } from "../../types";
import { citesTemplate } from "../../utils/citations";
import { formatDate } from "../../utils/format";
import {
  ArrowUpIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CloseIcon,
  ImageIcon,
  ImagePlusIcon,
  SettingsIcon,
  VideoIcon,
} from "../common/icons";
import {
  TokenizedPromptEditor,
  type PromptToken,
} from "../common/TokenizedPromptEditor";
import { SheetHandle } from "../common/SheetHandle";
import { TemplateList } from "../run/TemplateList";
import { AttachTiles, blockedReason, fallbackDropRole } from "./AttachTiles";
import { isNodeDrag, readNodeDrag } from "./dragRef";
import {
  MENU_MAX_H,
  ModelChip,
  ModelList,
  ParamChipRow,
  ProjectChip,
  ProjectList,
  TemplateChip,
  chipClass,
} from "./CreateChips";
import { AttachPicker } from "./AttachPicker";
import { SettingsPanel } from "./CreateSettings";
import { anyPending, castOf, defaultEntry, findEntry, locationsOf, sendsOf } from "./roles";
import { seedPlan } from "./seedPlan";
import { runPath, projectPath } from "../../utils/location";

/**
 * What `@character.N.…` may cite — the same six values a reference angle
 * fills from a bible. `build` and `must` name a variant, because the bible
 * answers both differently for a face than for a body.
 */
const CHARACTER_FIELDS = [
  "top",
  "style",
  "age",
  "identity_block",
  "build.face",
  "build.body",
  "must.face",
  "must.body",
];

/**
 * A draft made and held back, because its payload has been run here before.
 *
 * The fingerprint is the API's — computed from what actually landed, never
 * here — so the question "has this gone out before" can only be asked once a
 * draft exists. Holding it costs a row and no bytes; Send anyway submits it,
 * Discard deletes it.
 */
interface Held {
  draft: CreatedRun;
  twin: RunSummary;
}

const GLYPH = "size-4 fill-none stroke-current stroke-[1.5]";

/**
 * The create panel: what every screen makes runs from.
 *
 * **A frosted sheet under the header, always fully drawn** — the shape
 * ElevenLabs' runner has. It was a one-line box in the header that grew when
 * focused; a 72px header could hold nothing else, and the mode strip, the
 * picker and the settings each appeared and vanished with the caret. Then it
 * floated at the viewport's foot, over whatever was being looked at. Now the
 * shell mounts it in the flow at the top of the content column, the page
 * starts under it, and nothing about it is folded: the mode switch top-left,
 * the three icons top-right, a tile per image role, the prompt, and a row of
 * chips for the model and the settings worth a press — each a glyph and a
 * value that opens a short menu downward — and a gear holding every setting
 * as rows.
 * ⌘/Ctrl+Enter sends; Enter is a line break, a prompt being paragraphs. The
 * round arrow is Send.
 *
 * **There is no approve step.** Hard rule #2 is carried by the person
 * pressing Send over a prompt they can read.
 *
 * **When the row is too narrow for the chips they collapse into the gear**,
 * the way ElevenLabs' phone runner does: the model, the gear and Send. Below
 * `md` the gear opens a bottom sheet — the mode switch, a Model box, and every
 * setting as a row; above it, a panel of the same rows.
 *
 * **The state is not here.** `CreateBarContext` holds it so the feed can load
 * a run into the panel from a route element; this component reads it, draws
 * it, and does the one thing the context cannot: send.
 */
export function CreateBar() {
  const bar = useCreateBarState();
  const { attach, drop, setKind } = useCreateBar();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();

  const promptBox = useRef<HTMLDivElement>(null);
  const [promptFocused, setPromptFocused] = useState(false);
  /**
   * The sheet's own card, and whether the page has been scrolled past it.
   * While it has, `AttachDock` keeps the tiles on screen — see it for why.
   */
  const sheet = useRef<HTMLDivElement>(null);
  const scrolledPast = useScrolledPast(sheet);
  /**
   * Whether the dock is folded to its pill. Held here rather than in the
   * dock, because the dock is mounted only while the sheet is out of view:
   * a fold that undid itself every time the page was scrolled back up and
   * down again would be a decision that lasts one scroll.
   */
  const [dockFolded, setDockFolded] = useState(false);
  /**
   * **The caret is put in the prompt for you only under a mouse.** `loadRun`
   * and `expand` bump `bar.focus` so that Edit on a run, or pulling the sheet
   * up, lands you in the box — and on a phone that same bump raised the
   * keyboard over half the screen the moment Edit was pressed, before
   * anything had been read, with the tiles the person came to change
   * squeezed above it. Under a thumb the prompt takes focus when it is
   * tapped and not otherwise.
   */
  const fine = useMediaQuery(FINE);
  /**
   * Bumped when a press lands on the sheet outside the prompt — a tile, its
   * ×, the gear, Send — so the editor lets go. iOS keeps a contenteditable
   * focused, keyboard and all, through a tap on a `<button>`; and Lexical
   * would put the focus back on its next commit even where the browser had
   * dropped it (`blurKey` in `TokenizedPromptEditor`). On the pointer's way
   * down, so the keyboard is already going when the press does its work.
   */
  const [blurKey, setBlurKey] = useState(0);
  const leavePrompt = useCallback(() => {
    if (promptFocused) setBlurKey((n) => n + 1);
  }, [promptFocused]);
  // And when the picker opens by any path at all: on a phone it is a sheet
  // over this one, and a keyboard still up under it — the prompt's, kept
  // through the tap that opened it — covered the pictures it was opened for.
  const pickerOpen = bar.role !== null;
  useEffect(() => {
    if (pickerOpen && promptFocused) setBlurKey((n) => n + 1);
    // On the opening only — not on every keystroke while it is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickerOpen]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [sheetView, setSheetView] = useState<"settings" | "models" | "projects" | "templates">("settings");
  const sheetRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [held, setHeld] = useState<Held | null>(null);

  const attachments = bar.attachments[bar.kind];

  // The registry is per-deploy, so the key carries no id.
  const models = useResource(
    ["models"],
    useCallback(() => getModels(), []),
  );
  const target = bar.target;
  const project = useResource(
    target ? ["project", target] : null,
    useCallback(() => getProject(target ?? ""), [target]),
  );
  // The picker's list — asked for only when there is a picker to fill.
  const projects = useResource(
    bar.onProject ? null : ["projects"],
    useCallback(() => getProjects(), []),
  );
  // Blocks for the `{` menu and the preview.
  const templates = useResource(
    ["templates"],
    useCallback(() => getTemplates(), []),
  );

  // What this person starts each model at, over the registry's own defaults.
  // One read for the whole sheet; "Set as default" writes it back.
  const defaults = useResource(
    ["model-defaults"],
    useCallback(() => getModelDefaults(), []),
  );
  const own = useMemo(() => defaults.data?.defaults ?? {}, [defaults.data]);

  const entry =
    findEntry(models.data, bar.model[bar.kind]) ??
    defaultEntry(models.data, bar.kind);
  // Untouched this session: the model's defaults with the person's own laid
  // over — so a param the snapshot gained since they were saved still seeds.
  const params = useMemo(
    () =>
      entry
        ? (bar.params[entry.model] ?? { ...seedPlan(entry).params, ...own[entry.model] })
        : {},
    [bar.params, entry, own],
  );
  const projectCast = useMemo(
    () => project.data?.characters ?? [],
    [project.data],
  );
  const cast = useMemo(
    () => castOf(attachments, projectCast),
    [attachments, projectCast],
  );
  const projectLocations = useMemo(
    () => project.data?.locations ?? [],
    [project.data],
  );
  const shotIn = useMemo(
    () => locationsOf(attachments, projectLocations),
    [attachments, projectLocations],
  );

  const tokens = useMemo<PromptToken[]>(() => {
    const blocks = Object.entries(templates.data?.blocks ?? {}).sort(
      ([a], [b]) => a.localeCompare(b),
    );
    return [
      ...blocks.map(([name, text]) => ({
        name: `block.${name}`,
        kind: "block" as const,
        hint: text.slice(0, 60),
      })),
      ...cast.flatMap((_unused, i) =>
        CHARACTER_FIELDS.map((field) => ({
          name: `character.${i + 1}.${field}`,
          kind: "computed" as const,
          hint: `character ${i + 1}`,
        })),
      ),
    ];
  }, [cast, templates.data]);

  const prompt = bar.prompt.trim();
  // Not while something on the bar is still being made: a first frame the
  // worker has not handed back would be sent as nothing, silently.
  const pending = anyPending(attachments);
  const canSend = Boolean(entry && target && prompt !== "") && !busy && !pending;

  /**
   * A template picked lands FILLED, not as the citations it was written with.
   *
   * **The box is the preview now.** A template is mostly `@block.…` and
   * `@character.N.…`, so picking one used to put a prompt in the bar that
   * said almost nothing about what the model would be told; reading it took a
   * second popover holding a second rendering of the same prompt. Filling at
   * the pick collapses the two: what is in the box is what goes out, and it is
   * editable prose rather than a citation a person cannot see inside.
   *
   * **Filled by the API, never here.** `POST /api/templates/expand` runs the
   * same `expand` a draft's save runs. Filling blocks in the client would be a
   * second opinion about what a run was told to render, and the disagreement
   * would be invisible afterwards because a run records the outcome and not the
   * reasoning.
   *
   * **A fill that cannot be done leaves the template.** A prompt citing
   * `@character.2.…` against a one-character run is a 400 naming the
   * citation; the words land in the box as written so the cast can be added
   * and the prompt sent, and the refusal is said rather than swallowed.
   *
   * **The box is written once, when the answer is known.** Putting the raw
   * template in first and replacing it on the reply loses a race: the editor
   * echoes each value it is given back through `onValueChange`, and the echo
   * of the template arrives after the filled prompt was set — so the box ends
   * up holding the citations again.
   */
  const pickTemplate = useCallback(
    async (template: string) => {
      // Nothing to fill, nothing to ask: a template of plain prose is its own
      // finished prompt. **A brace is not a citation** — a template written as
      // JSON, or one carrying a stray `{`, is prose by this test and stays
      // exactly as written.
      if (!citesTemplate(template)) {
        bar.setPrompt(template);
        return;
      }
      try {
        const filled = await expandTemplate(template, cast);
        bar.setPrompt(filled.prompt);
      } catch (err) {
        bar.setPrompt(template);
        toast.add({
          intent: "warning",
          title: "Left as written",
          description: (err as Error).message,
          // Nothing dismisses it on a timer: it names a citation the person
          // has to do something about before this prompt is worth sending.
          duration: 0,
        });
      }
    },
    [bar, cast, toast],
  );

  /**
   * Send: a draft, then the duplicate question, then the submit.
   *
   * **The draft is created whole.** `POST /api/runs` takes the plan and the
   * sends together, so what the fingerprint hashes is what was in the panel.
   * A prompt that cites a block or a character goes through `PATCH /plan`
   * too, because that is the route that expands a template into the prompt
   * the model sees — creation stores the plan as given.
   *
   * The template is the instruction and not a field: `PATCH /plan` expands it
   * into `prompt` and stores only that, so what the fingerprint covers is the
   * words the model gets however they were written.
   *
   * **"Cites anything" is `citesTemplate`, not a brace.** It was
   * `prompt.includes("{")`, and `studio prompt` writes a prompt as serialised
   * JSON — so every structured prompt went out as a template and came back
   * refused for citing `{ "subject"}`. A JSON prompt cites nothing, skips
   * `PATCH /plan`, and is sent as the words it is.
   *
   * **Then one cheap read.** `?fingerprint=` is one query on the listing row.
   * A twin that was actually sent holds the draft and asks; a draft or a
   * discard is not a twin, because nothing was spent on it.
   */
  const send = useCallback(
    async (force = false) => {
      if (!entry || !target || prompt === "" || busy || anyPending(attachments)) return;
      setBusy(true);
      setFailure(null);
      try {
        let draft = held?.draft ?? null;
        let fingerprint = draft?.fingerprint ?? null;
        if (!draft) {
          const cited = citesTemplate(prompt);
          const created = await createRun({
            project: target,
            // On a scene page the draft is the scene's from the start.
            ...(bar.scene ? { scene: bar.scene } : {}),
            kind: entry.kind,
            // The Replicate `owner/name`, not the registry key — `POST /api/runs`
            // records the model the provider is called by.
            model: entry.model,
            engine: entry.skill,
            ...(cast.length ? { characters: cast } : {}),
            ...(shotIn.length ? { locations: shotIn } : {}),
            plan: { version: 1, origin: "authored", prompt, params },
            sends: sendsOf(attachments, entry),
          });
          draft = created;
          fingerprint = created.fingerprint;
          if (cited) {
            const expanded = await patchRunPlan(created.id, {
              version: 1,
              origin: "authored",
              template: prompt,
              prompt,
              params,
            });
            fingerprint = expanded.fingerprint ?? fingerprint;
          }
        }
        if (!force && fingerprint) {
          const page = await getRuns({
            project: target,
            fingerprint,
            include: "drafts",
          });
          const twin = page.runs.find(
            (other) =>
              other.id !== draft!.id &&
              other.status !== "draft" &&
              other.status !== "discarded",
          );
          if (twin) {
            setHeld({ draft, twin });
            return;
          }
        }
        await submitRun(draft.id);
        setHeld(null);
        bar.sent();
        toast.add({
          intent: "success",
          title: "Sent",
          description: `${entry.key} in ${project.data?.name ?? "the project"}.`,
        });
        // Every feed and listing keyed under `runs`, and the project's counts.
        void queryClient.invalidateQueries({ queryKey: ["runs"] });
        void queryClient.invalidateQueries({ queryKey: ["project", target] });
        if (bar.scene) void queryClient.invalidateQueries({ queryKey: ["scene", bar.scene] });
        if (!bar.onProject) navigate(projectPath(target));
      } catch (err) {
        setFailure((err as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [
      attachments,
      bar,
      busy,
      cast,
      entry,
      held,
      navigate,
      params,
      project.data?.name,
      prompt,
      queryClient,
      shotIn,
      target,
      toast,
    ],
  );

  const discard = useCallback(async () => {
    if (!held) return;
    setBusy(true);
    try {
      await deleteRun(held.draft.id, "delete");
      setHeld(null);
    } catch (err) {
      setFailure((err as Error).message);
    } finally {
      setBusy(false);
    }
  }, [held]);

  const placeholder = bar.scene
    ? "Describe what to make for this scene…"
    : project.data
    ? `Describe what to make in ${project.data.name}…`
    : target
      ? "Describe what to make…"
      : "Pick a project, then describe what to make…";

  const setParams = (next: Record<string, unknown>) => {
    if (entry) bar.setParams(entry.model, next);
  };

  /**
   * The two things the settings panel can do with the whole set. Both
   * write the person's row, then put the answer straight into the query so
   * every sheet reads it without a refetch.
   */
  const rememberDefaults = (held: ModelDefaults) =>
    queryClient.setQueryData(["model-defaults"], { defaults: held });
  const saveAsDefault = async () => {
    if (!entry) return;
    try {
      const written = await setModelDefaults(entry.model, params);
      rememberDefaults({ ...own, [written.model]: written.params });
      toast.add({ intent: "success", title: `Saved as your default for ${entry.key}` });
    } catch (err) {
      toast.add({ intent: "danger", title: "Could not save the default", description: (err as Error).message });
    }
  };
  const resetToModel = async () => {
    if (!entry) return;
    try {
      await clearModelDefaults(entry.model);
      rememberDefaults(Object.fromEntries(Object.entries(own).filter(([model]) => model !== entry.model)));
      bar.setParams(entry.model, seedPlan(entry).params);
    } catch (err) {
      toast.add({ intent: "danger", title: "Could not reset the settings", description: (err as Error).message });
    }
  };
  const settingsActions = entry
    ? {
        saved: entry.model in own,
        onSaveDefault: () => void saveAsDefault(),
        onReset: () => void resetToModel(),
      }
    : null;

  const kindSwitch = (
    // IMAGE / VIDEO. Single-select and never empty: a run is one or the other,
    // and the tiles under the switch are drawn from it.
    <ToggleGroup.Root
      aria-label="Kind"
      value={[bar.kind]}
      onValueChange={(next: string[]) => {
        const chosen = next[0];
        if (chosen === "image" || chosen === "video") setKind(chosen);
      }}
      size="sm"
      className="gap-0.5 rounded-sm bg-fill p-0.5"
    >
      <Toggle value="image" className={pillClass(bar.kind === "image")}>
        <ImageIcon className={GLYPH} />
        Image
      </Toggle>
      <Toggle value="video" className={pillClass(bar.kind === "video")}>
        <VideoIcon className={GLYPH} />
        Video
      </Toggle>
    </ToggleGroup.Root>
  );

  // Off a project page the panel has to be told where a run goes; on one,
  // the route says. A chip in the row on every width — `ProjectChip` says
  // why it is no longer a box of its own.
  const projectPicker = !bar.onProject && (
    <ProjectChip
      projects={projects.data ?? []}
      value={target ?? null}
      onProject={(id) => bar.setProject(id)}
    />
  );

  if (!bar.shown) return null;

  /**
   * A picture dropped on the sheet but on no tile still lands — as whatever
   * role the model has room for, references first (`fallbackDropRole`). The
   * tiles answer a drop that named its role before it reaches here and stop
   * it; this is for the drop that did not, which is most of them now that a
   * drag from a viewer brings the sheet up under the pointer.
   */
  const dropRole = entry ? fallbackDropRole(bar.kind, entry, attachments) : null;
  // Why the open picker's role can take no more — `max_refs` met, a frame
  // excluding references — or null while it can. Read on every render so the
  // picker closes its tiles the moment the cap is reached, not on reopen.
  const pickerFull = entry && bar.role ? blockedReason(bar.role, entry, attachments) : null;
  const onDragOver = (event: DragEvent) => {
    if (!isNodeDrag(event) || dropRole === null) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  };
  const onDrop = (event: DragEvent) => {
    if (dropRole === null) return;
    const ref = readNodeDrag(event);
    if (!ref) return;
    event.preventDefault();
    attach(ref, dropRole);
  };

  return (
    <div
      className="flex flex-col gap-2"
      data-create-bar=""
      onDragOver={onDragOver}
      onDrop={onDrop}
      onKeyDown={(event) => {
        // Escape inside the sheet puts it away on the opened run — inside, so
        // it never competes with the Escape a viewer, a drawer or a menu
        // binds for itself. Anywhere else the sheet is not something that
        // goes away, and Escape is nothing here.
        if (event.key === "Escape" && !event.defaultPrevented) bar.dismiss();
      }}
    >
      {held && (
        <Alert.Root intent="warning">
          <Alert.Title>This request has been run here before</Alert.Title>
          <Alert.Description>
            <span>
              Another run in this project sent exactly this prompt, these
              parameters and these images on {formatDate(held.twin.created)}.
              Sending again bills again — a model answers differently every
              time, so a second attempt is often the point.{" "}
            </span>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" disabled={busy} onClick={() => void send(true)}>
                Send anyway
              </Button>
              <Button
                size="sm"
                intent="secondary"
                disabled={busy}
                onClick={() => void discard()}
              >
                Discard
              </Button>
              <Button
                size="sm"
                intent="secondary"
                onClick={() => navigate(runPath(held.twin.project, held.twin.id))}
              >
                Open the earlier run
              </Button>
            </div>
          </Alert.Description>
        </Alert.Root>
      )}

      {failure && (
        <Alert.Root intent="danger">
          <Alert.Title>Could not send this run</Alert.Title>
          <Alert.Description>{failure}</Alert.Description>
        </Alert.Root>
      )}

      {/* The picker: a drawer while a tile is highlighted, holding the
          library's file navigation. A drawer rather than a card hung off
          the sheet, so it opens the same from the dock once the sheet has
          scrolled away — see `AttachPicker`. */}
      {bar.role !== null && entry && (
        <AttachPicker
          key={bar.role}
          role={bar.role}
          project={
            project.data
              ? {
                  kind: "project",
                  id: project.data.id,
                  name: project.data.name,
                  root: project.data.root,
                }
              : null
          }
          attached={new Set(attachments.map((each) => each.ref.node))}
          held={attachments.filter((each) => each.role === bar.role).length}
          cap={bar.role === "reference" ? (entry?.images?.max_refs ?? null) : null}
          full={pickerFull}
          onAttach={(ref: AttachRef) => {
            // The tiles are disabled once `full` is set; this is the
            // same rule for a press that raced the render.
            if (bar.role && pickerFull === null) attach(ref, bar.role);
          }}
          // The mark in the picker means "on the sheet", in any role, so
          // pressing it again takes the picture off whichever role holds it.
          onDetach={drop}
          onClose={() => bar.setRole(null)}
        />
      )}

      {/* The sheet. `bg-sheet` over a blur rather than a solid, kept from
          when it floated: the dock and the picker are the same material,
          and the three should read as one thing.

          **A card on the page**, a line below the header and inside the
          page's gutters, so every corner is rounded. */}
      <div
        ref={sheet}
        className="flex flex-col gap-3 rounded-lg bg-sheet p-3 shadow-[0_8px_48px_rgba(0,0,0,0.55)]
                   ring-1 ring-line backdrop-blur-xl"
      >
        <div className="flex items-center justify-between gap-2" onPointerDownCapture={leavePrompt}>
          {kindSwitch}

          {/* **Only over the viewer.** On a page the sheet is part of the
              page and there is nothing to close; on the opened run it was
              called up over a fixed-height viewer, and the thing that called
              it up should have a way back. Escape does the same. */}
          {bar.overViewer && (
            <IconButton size="sm" label="Close the create panel" onClick={bar.dismiss}>
              <CloseIcon />
            </IconButton>
          )}
        </div>

        {entry && (
          <div className="contents" onPointerDownCapture={leavePrompt}>
            <AttachTiles
              kind={bar.kind}
              entry={entry}
              attachments={attachments}
              role={bar.role}
              onRole={bar.setRole}
              onDetach={bar.detach}
              onSwapFrames={bar.swapFrames}
              onMove={bar.move}
              // A picture dragged out of the library's grid and dropped on a
              // role tile. `attach` is the same call the tiles' own button
              // makes; what the drop adds is that the gesture NAMES the role.
              onDropRef={attach}
            />
          </div>
        )}

        {/* As tall as the prompt. It used to be two lines at rest and eight
            with the caret in it, because the sheet was pinned to the foot of
            the viewport and a long prompt made it half the screen; since the
            card sits in the page's flow, the page scrolls instead. Focus is
            tracked on the box rather than read off the editor: React hears
            `focusin`/`focusout`. */}
        <div
          ref={promptBox}
          className="px-1"
          onFocusCapture={() => setPromptFocused(true)}
          onBlurCapture={(event) => {
            if (!promptBox.current?.contains(event.relatedTarget as Node | null))
              setPromptFocused(false);
          }}
        >
          <TokenizedPromptEditor
            value={bar.prompt}
            onValueChange={bar.setPrompt}
            tokens={tokens}
            ariaLabel="Prompt"
            placeholder={placeholder}
            className=""
            family="body"
            menuSide="down"
            contentClassName="min-h-12"
            onSubmit={() => void send()}
            focusKey={fine ? bar.focus : undefined}
            blurKey={blurKey}
          />
        </div>

        {/* `@container`: the chips show only when the row is wide enough for
            them (`@min-[40rem]`), and collapse into the gear otherwise. A
            container query rather than `md:`, because a narrow window with the
            sidebar open is the phone's problem at a desktop breakpoint. */}
        <div className="@container flex items-center gap-1" onPointerDownCapture={leavePrompt}>
          {projectPicker}

          {entry && (
            <ModelChip
              kind={bar.kind}
              models={models.data ?? {}}
              entry={entry}
              onModel={bar.setModel}
            />
          )}

          <TemplateChip cast={cast.length} onPick={(prompt: string) => void pickTemplate(prompt)} />

          {entry && (
            <ParamChipRow
              entry={entry}
              params={params}
              onParams={setParams}
              className="hidden @min-[40rem]:flex"
            />
          )}

          {/* The gear, from `lg`: every setting as rows, in a panel hung
              from the chip row. The same rows the sheet draws — the six
              chips' and the rest of the schema's — so when the chips have
              collapsed into it nothing is out of reach. `lg` rather than
              `md` because a tablet's row has no room for the panel on
              either side of the gear — see `ROOMY`. */}
          {entry && (
            <Popover.Root open={settingsOpen} onOpenChange={setSettingsOpen}>
              <Popover.Trigger
                aria-label="Settings"
                title="Settings"
                className={`${chipClass} max-lg:hidden`}
              >
                <SettingsIcon className={GLYPH} />
              </Popover.Trigger>
              <Popover.Content
                label="Settings"
                // Hung from the gear's LEFT edge, like every other chip's
                // menu. It hung from the right while the gear was the row's
                // last control; now the chips sit left of the Send arrow, and
                // a 26rem panel right-anchored to a chip a third of the way
                // across ran under the sidebar on a tablet.
                className={`mt-2 ${MENU_MAX_H} w-[min(26rem,calc(100vw-2rem))] max-w-none overflow-y-auto`}
              >
                <SettingsPanel entry={entry} params={params} onParams={setParams} actions={settingsActions} />
              </Popover.Content>
            </Popover.Root>
          )}

          {/* The gear under `lg`: the sheet. Two views — the settings as rows,
              and "Select a model" in its place when the Model row is pressed,
              the way ElevenLabs pages the same sheet rather than stacking a
              picker over it.

              **Capped in `dvh`, scrolling inside under a stuck grab strip.**
              `85vh` was the viewport with Safari's bars hidden, so with them
              shown the sheet's top — and its grab strip — sat under the
              address bar. The strip is `sticky`, so a sheet scrolled to its
              last row still has the thing that dismisses it; the backdrop
              and Escape do too. A `Done` at the foot was tried and was one
              control more than the sheet needed. */}
          <Drawer.Root
            side="bottom"
            open={sheetOpen}
            onOpenChange={(next: boolean) => {
              setSheetOpen(next);
              if (!next) setSheetView("settings");
            }}
          >
            <Drawer.Trigger
              aria-label="Settings"
              title="Settings"
              className={`${chipClass} bg-fill lg:hidden`}
            >
              <SettingsIcon className={GLYPH} />
            </Drawer.Trigger>
            <Drawer.Backdrop />
            <Drawer.Panel
              ref={sheetRef}
              className="max-h-[85dvh] overflow-y-auto overscroll-contain rounded-t-lg pt-0"
            >
              <Drawer.Title className="sr-only">
                {sheetView === "models"
                  ? "Select a model"
                  : sheetView === "projects"
                    ? "Select a project"
                    : sheetView === "templates"
                      ? "Start from a template"
                      : "Settings"}
              </Drawer.Title>
              <SheetHandle panel={sheetRef} onDismiss={() => setSheetOpen(false)} />
              {/* The project page, the same shape as the model's: off a
                  project page the sheet has to say where a run goes, and
                  the chip in the row is the same question asked the same
                  way. Not drawn on a project page, where the route answers. */}
              {sheetView === "projects" ? (
                <div className="flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <IconButton size="sm" label="Back to settings" onClick={() => setSheetView("settings")}>
                      <ChevronLeftIcon />
                    </IconButton>
                    <Text as="span" variant="body" weight="medium">
                      Select a project
                    </Text>
                  </div>
                  <ProjectList
                    projects={projects.data ?? []}
                    value={target ?? null}
                    autoFocus={fine}
                    onProject={(id) => {
                      bar.setProject(id);
                      setSheetView("settings");
                    }}
                  />
                </div>
              ) : sheetView === "templates" ? (
                <div className="flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <IconButton size="sm" label="Back to settings" onClick={() => setSheetView("settings")}>
                      <ChevronLeftIcon />
                    </IconButton>
                    <Text as="span" variant="body" weight="medium">
                      Start from a template
                    </Text>
                  </div>
                  {/* Picking fills the prompt and closes the sheet: the
                      prompt is what the pick is for, and it is behind the
                      sheet until the sheet goes. */}
                  <TemplateList
                    cast={cast.length}
                    onPick={(prompt) => {
                      void pickTemplate(prompt);
                      setSheetOpen(false);
                      setSheetView("settings");
                    }}
                  />
                </div>
              ) : entry && sheetView === "models" ? (
                <div className="flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <IconButton size="sm" label="Back to settings" onClick={() => setSheetView("settings")}>
                      <ChevronLeftIcon />
                    </IconButton>
                    <Text as="span" variant="body" weight="medium">
                      Select a model
                    </Text>
                  </div>
                  <ModelList
                    kind={bar.kind}
                    models={models.data ?? {}}
                    entry={entry}
                    // Under a mouse the caret goes to the search; under a
                    // thumb that is the keyboard over the list it searches.
                    autoFocus={fine}
                    onModel={(model) => {
                      bar.setModel(model);
                      setSheetView("settings");
                    }}
                  />
                </div>
              ) : (
                <div className="flex flex-col gap-5">
                  {/* **Two sections.** What the run IS — its kind, where it
                      goes, which model, a template to start from — and then
                      the model's own settings, under a rule and a heading
                      that names the model. The three rows are the row of
                      chips as a list; the settings change with the model
                      picked above them, and the rule says which half is
                      whose. */}
                  <div className="flex flex-col gap-4">
                    <div className="[&>div]:w-full [&>div>button]:flex-1">{kindSwitch}</div>
                    {!bar.onProject && (
                      <SheetRow label="Project" onPress={() => setSheetView("projects")}>
                        {projects.data?.find((each) => each.id === target)?.name ?? "Pick a project"}
                      </SheetRow>
                    )}
                    {entry && (
                      <SheetRow label="Model" onPress={() => setSheetView("models")}>
                        {entry.key}
                      </SheetRow>
                    )}
                    {/* No value to show — picking one fills the prompt and
                        stops, so there is no "current template" — hence the
                        verb, in the muted tone a placeholder takes. */}
                    <SheetRow label="Template" onPress={() => setSheetView("templates")}>
                      <span className="text-muted">Start from a template</span>
                    </SheetRow>
                  </div>
                  {entry && (
                    <div className="flex flex-col gap-2 border-t border-line pt-4">
                      <Text as="span" variant="caption" tone="muted">
                        {entry.key} settings
                      </Text>
                      <SettingsPanel entry={entry} params={params} onParams={setParams} actions={settingsActions} />
                    </div>
                  )}
                </div>
              )}
            </Drawer.Panel>
          </Drawer.Root>

          <span className="flex-1" />

          {/* Round, white, an arrow — the one filled control on the sheet.
              The word is for assistive tech; the shape is the word for
              everyone else. */}
          <Button
            size="sm"
            aria-label={busy ? "Sending…" : pending ? "Waiting for a frame…" : "Send"}
            title={pending ? "Waiting for the first frame to land" : `Send (${navigator.platform.startsWith("Mac") ? "⌘" : "Ctrl"}+Enter)`}
            className="size-9 shrink-0 rounded-pill p-0"
            disabled={!canSend}
            onClick={() => void send()}
          >
            <ArrowUpIcon className="size-5 fill-none stroke-current stroke-2" />
          </Button>
        </div>
      </div>

      {/* **The sheet's pictures stay on screen once the sheet has scrolled
          off.** The point of the tiles is that a picture anywhere in the
          feed can be dragged onto one — and the feed is under the sheet, so
          the moment the person has scrolled to the picture they want, the
          tiles have gone. The dock is the same tiles, fixed in the window's
          top-right corner while the sheet is out of view, with the way back
          up beside them. Inside the bar's own box so a drop on the dock
          that named no tile still lands as the sheet's fallback role, and
          `attach` does not scroll the page: a drop has to leave the dock
          where the next drag will find it. */}
      {scrolledPast && entry && (
        <AttachDock
          held={attachments}
          folded={dockFolded}
          onFold={setDockFolded}
          onBack={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        >
          <AttachTiles
            kind={bar.kind}
            entry={entry}
            attachments={attachments}
            role={bar.role}
            // The picker is a drawer, so it opens from here as it does
            // from the sheet — nothing about it needs the page back up.
            onRole={bar.setRole}
            onDetach={bar.detach}
            onSwapFrames={bar.swapFrames}
            onMove={bar.move}
            onDropRef={attach}
          />
        </AttachDock>
      )}
    </div>
  );
}

/**
 * One row of the gear sheet's first section: a word over a full-width box
 * with a chevron, which pages the sheet to a list — the shape ElevenLabs'
 * sheet gives "Model". The project, the model and the template share it.
 */
function SheetRow({ label, onPress, children }: { label: string; onPress: () => void; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Text as="span" variant="body">
        {label}
      </Text>
      <Button
        intent="secondary"
        size="md"
        className="w-full justify-between rounded-md border border-line bg-transparent px-3 font-normal"
        onClick={onPress}
      >
        <span className="truncate">{children}</span>
        <ChevronRightIcon className="size-4 shrink-0 fill-none stroke-current stroke-[1.5] text-muted" />
      </Button>
    </div>
  );
}

/**
 * The frame the dock draws: a card in the window's corner under the header,
 * the tiles on the left and the up-arrow on the right. The whole window's
 * width on a phone, shrink-to-fit on a desk up to the window less the rail
 * and a gutter — the tile row scrolls sideways past that, as it does in the
 * sheet. It was capped at 40rem, which showed three pictures where the sheet
 * had shown six. The tiles are the compact size (`data-compact`, 80px):
 * this is a strip to drop onto, not the sheet, and at the sheet's size a
 * phone showed one picture.
 *
 * **The arrow is last in both states**, so it stays under the thumb when
 * the dock folds and unfolds: the card is anchored to the right edge, and
 * the rightmost control is the one that does not move.
 *
 * **It folds into the arrow.** A × at the row's end puts the tiles away and
 * leaves a short pill: the arrow, which still goes to the top, and beside it
 * what was folded — the first held picture, or the picture glyph when
 * nothing is held, with a count — which unfolds it. Not a chevron: the
 * thing that brings the tiles back should look like the tiles, and a row of
 * arrows read as noise. The × is inside the card, not on its corner: hung
 * off the corner it grew to its 44px floor under a thumb and stood clear of
 * the card, reading as a stray control rather than the card's own.
 *
 * Folded stays folded across scrolls — the state is the bar's, not this
 * component's, which is mounted afresh each time the sheet leaves the view.
 * It unfolds the moment a picture is picked up anywhere, because a drag with
 * nowhere to land is a gesture that does nothing and the tiles are the only
 * place a drop lands.
 */
function AttachDock({
  children,
  held,
  folded: collapsed,
  onFold: setCollapsed,
  onBack,
}: {
  children: ReactNode;
  /** What the dock holds, for the folded pill: the first picture and the count. */
  held: readonly Attachment[];
  folded: boolean;
  onFold: (folded: boolean) => void;
  onBack: () => void;
}) {
  const first = held.find((each) => each.ref.url) ?? null;

  useEffect(() => {
    if (!collapsed) return;
    const onDragEnter = (event: globalThis.DragEvent) => {
      if (isNodeDrag(event)) setCollapsed(false);
    };
    window.addEventListener("dragenter", onDragEnter);
    return () => window.removeEventListener("dragenter", onDragEnter);
  }, [collapsed, setCollapsed]);

  const back = (
    <IconButton size="md" label="Back to the create panel" onClick={onBack}>
      <ArrowUpIcon className={GLYPH} />
    </IconButton>
  );

  return (
    <div
      data-create-dock=""
      data-collapsed={collapsed ? "" : undefined}
      className={`fixed z-30 md:left-auto md:right-4 md:w-auto md:max-w-[calc(100vw-6rem)] ${
        collapsed ? "right-4" : "inset-x-4"
      }`}
      // A hair under the header: the card is the sheet's stand-in, not a
      // toast, so it sits close to the bar rather than a line below it —
      // but not flush, which read as part of the bar.
      style={{ top: "calc(var(--header-h) + 0.25rem)" }}
    >
      {collapsed ? (
        <div
          className="flex items-center gap-1 rounded-pill bg-sheet p-1 shadow-[0_8px_24px_rgba(0,0,0,0.45)]
                     ring-1 ring-line backdrop-blur-xl"
        >
          {/* The folded tiles, as one press: the first picture (or the
              glyph) and how many are held. */}
          <Button
            intent="ghost"
            size="sm"
            aria-label={`Show the attached pictures (${held.length})`}
            title="Show the attached pictures"
            className="h-9 gap-1.5 rounded-pill px-1.5 pr-2.5"
            onClick={() => setCollapsed(false)}
          >
            {first?.ref.url ? (
              <img src={first.ref.url} alt="" className="size-7 rounded-sm object-cover" />
            ) : (
              <ImagePlusIcon className={GLYPH} />
            )}
            <span className="text-sm tabular-nums">{held.length}</span>
          </Button>
          {back}
        </div>
      ) : (
        <div
          className="flex items-center gap-1 rounded-lg bg-sheet p-1.5 shadow-[0_8px_32px_rgba(0,0,0,0.55)]
                     ring-1 ring-line backdrop-blur-xl"
        >
          <div className="min-w-0 flex-1" data-compact="">
            {children}
          </div>
          <IconButton size="sm" label="Hide the attached pictures" onClick={() => setCollapsed(true)}>
            <CloseIcon className={GLYPH} />
          </IconButton>
          {back}
        </div>
      )}
    </div>
  );
}

/**
 * One half of the mode switch. The package's pressed state is the primary
 * fill — white on this palette — and ElevenLabs' is a lighter grey in the
 * same track, so the pressed classes are overridden here.
 */
function pillClass(on: boolean): string {
  return `h-7 gap-1.5 rounded-md px-2.5 text-sm ${
    on
      ? "bg-fill-active text-ink hover:bg-fill-active active:bg-fill-active"
      : "text-muted hover:bg-fill hover:text-ink"
  }`;
}

