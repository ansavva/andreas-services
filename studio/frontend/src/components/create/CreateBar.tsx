import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  Alert,
  Badge,
  Button,
  Combobox,
  Popover,
  Text,
  Toggle,
  ToggleGroup,
  iconButtonClass,
  useToast,
  type ComboboxOption,
} from "@ansavva/design-system";

import {
  createRun,
  deleteRun,
  getModels,
  getProject,
  getProjects,
  getRuns,
  getTemplates,
  patchRunPlan,
  submitRun,
} from "../../apis/studio";
import {
  useCreateBar,
  useCreateBarState,
  type AttachRef,
} from "../../context/CreateBarContext";
import { useResource } from "../../hooks/useResource";
import type { CreatedRun, RunSummary } from "../../types";
import { formatDate } from "../../utils/format";
import {
  EyeIcon,
  ImageIcon,
  SendIcon,
  SlidersIcon,
  VideoIcon,
} from "../common/icons";
import { PromptPreview } from "../common/PromptPreview";
import {
  TokenizedPromptEditor,
  type PromptToken,
} from "../common/TokenizedPromptEditor";
import { unfilledIn } from "../common/UnfilledMarks";
import { TemplatePicker } from "../run/TemplatePicker";
import { CreateDrawer } from "./CreateDrawer";
import { CreateModeStrip } from "./CreateModeStrip";
import { CreateSettings } from "./CreateSettings";
import { castOf, defaultEntry, findEntry, sendsOf } from "./roles";
import { seedPlan } from "./seedPlan";
import { runPath, projectPath } from "../../utils/location";

/**
 * What `{character.N.…}` may cite — the same six values a reference angle
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

/**
 * The create bar: what every screen makes runs from.
 *
 * **One box at the top, always.** The old flow was a `New run` button, a
 * drawer asking three questions, a navigation to a draft's page and an editor
 * there; this is the tokenized prompt editor with the kind switch beside it,
 * the images under it and the parameters behind an icon. Enter sends. There
 * is no approve step — hard rule #2 is carried by the person pressing Send
 * over a prompt they can read.
 *
 * **At rest it is one row.** The action row, the mode strip and the drawer
 * appear while the bar is *active* — focus is inside it, or one of its own
 * popovers or the duplicate warning is open — and go the moment a press lands
 * anywhere else, whatever the bar still holds. The prompt stays readable in
 * the row; images it holds are counted beside the settings icon so a Send
 * from the collapsed row is never a surprise.
 *
 * **The state is not here.** `CreateBarContext` holds it so the feed can load
 * a run into the bar from a route element; this component reads it, draws it,
 * and does the one thing the context cannot: send.
 */
export function CreateBar() {
  const bar = useCreateBarState();
  const { attach, setKind } = useCreateBar();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();

  const [focused, setFocused] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [held, setHeld] = useState<Held | null>(null);

  const attachments = bar.attachments[bar.kind];
  const active = focused || previewOpen || settingsOpen || held !== null;

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
  // Blocks for the `{` menu and the preview. Lazily: a bar nobody has touched
  // has no reason to read the template library.
  const templates = useResource(
    active ? ["templates"] : null,
    useCallback(() => getTemplates(), []),
  );

  const entry =
    findEntry(models.data, bar.model[bar.kind]) ??
    defaultEntry(models.data, bar.kind);
  const params = useMemo(
    () => (entry ? (bar.params[entry.model] ?? seedPlan(entry).params) : {}),
    [bar.params, entry],
  );
  const projectCast = useMemo(
    () => project.data?.characters ?? [],
    [project.data],
  );
  const cast = useMemo(
    () => castOf(attachments, projectCast),
    [attachments, projectCast],
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

  const unfilled = useMemo(() => unfilledIn(bar.prompt), [bar.prompt]);
  const lines = bar.prompt === "" ? 0 : bar.prompt.split("\n").length;
  const prompt = bar.prompt.trim();
  const canSend = Boolean(entry && target && prompt !== "") && !busy;

  /**
   * Send: a draft, then the duplicate question, then the submit.
   *
   * **The draft is created whole.** `POST /api/runs` takes the plan and the
   * sends together, so what the fingerprint hashes is what was in the bar. A
   * prompt that cites a block or a character goes through `PATCH /plan` too,
   * because that is the route that expands a template into the prompt the
   * model sees — creation stores the plan as given.
   *
   * **Then one cheap read.** `?fingerprint=` is one query on the listing row.
   * A twin that was actually sent holds the draft and asks; a draft or a
   * discard is not a twin, because nothing was spent on it.
   */
  const send = useCallback(
    async (force = false) => {
      if (!entry || !target || prompt === "" || busy) return;
      setBusy(true);
      setFailure(null);
      try {
        let draft = held?.draft ?? null;
        let fingerprint = draft?.fingerprint ?? null;
        if (!draft) {
          const cited = prompt.includes("{");
          const created = await createRun({
            project: target,
            kind: entry.kind,
            // The Replicate `owner/name`, not the registry key — `POST /api/runs`
            // records the model the provider is called by.
            model: entry.model,
            engine: entry.skill,
            ...(cast.length ? { characters: cast } : {}),
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

  const projectOptions = useMemo<ComboboxOption[]>(
    () =>
      (projects.data ?? []).map((each) => ({
        value: each.id,
        label: each.name,
      })),
    [projects.data],
  );

  const placeholder = project.data
    ? `Describe what to make in ${project.data.name}…`
    : target
      ? "Describe what to make…"
      : "Pick a project, then describe what to make…";

  return (
    <div
      // The slot keeps its resting height whatever the bar is doing. Once
      // active the box FLOATS over the page: the action row, the strip, the
      // drawer and a taller prompt all grow downwards over the content, and
      // nothing beneath the sticky header moves. 50px is the resting box: a
      // 44px control row, its 2px of vertical padding and the two borders.
      className="relative min-h-[50px] min-w-0 flex-1"
      data-create-bar=""
      onFocus={() => setFocused(true)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          setFocused(false);
      }}
    >
      <div
        className={
          active
            ? "absolute inset-x-0 top-0 z-30 flex flex-col"
            : "flex flex-col"
        }
      >
        <div
          className={`flex flex-col rounded-none border bg-card ${active ? "border-ink" : "border-line"}`}
        >
          <div className="flex items-start gap-2 py-0.5 pl-0.5 pr-2">
            {/* IMAGE / VIDEO. Single-select and never empty: a run is one or
              the other, and the strip under the bar is drawn from it. */}
            <ToggleGroup.Root
              aria-label="Kind"
              value={[bar.kind]}
              onValueChange={(next: string[]) => {
                const chosen = next[0];
                if (chosen === "image" || chosen === "video") setKind(chosen);
              }}
              // `sm`: two 32px squares. At 390px the row also holds the menu
              // button and the search icon, and two 44s would push it over.
              size="sm"
              className="mt-1 shrink-0 gap-0 border-r border-line pr-1"
            >
              <Toggle
                value="image"
                iconOnly
                label="Image"
                className="rounded-none"
              >
                <ImageIcon />
              </Toggle>
              <Toggle
                value="video"
                iconOnly
                label="Video"
                className="rounded-none"
              >
                <VideoIcon />
              </Toggle>
            </ToggleGroup.Root>

            {/* Off a project page the bar has to be told where a run goes. On
              one, the route says. Inline above `md`; on a phone the picker
              takes a row of its own under the prompt, below. */}
            {!bar.onProject && (
              <div className="hidden w-40 shrink-0 self-center md:block">
                <Combobox
                  aria-label="Project"
                  options={projectOptions}
                  value={target ?? null}
                  placeholder="Project"
                  onValueChange={(next: string) => bar.setProject(next || null)}
                />
              </div>
            )}

            <div className="min-w-0 flex-1 py-2.5">
              <TokenizedPromptEditor
                value={bar.prompt}
                onValueChange={bar.setPrompt}
                tokens={tokens}
                ariaLabel="Prompt"
                placeholder={placeholder}
                className=""
                // One line at rest; eight before it scrolls.
                contentClassName="min-h-6 max-h-48 overflow-y-auto"
                onSubmit={() => void send()}
                focusKey={bar.focus}
              />
            </div>

            {!active && attachments.length > 0 && (
              <Badge size="sm" className="mt-3 shrink-0 rounded-none">
                {attachments.length}{" "}
                {attachments.length === 1 ? "image" : "images"}
              </Badge>
            )}

            <Popover.Root open={settingsOpen} onOpenChange={setSettingsOpen}>
              <Popover.Trigger
                aria-label="Settings"
                title="Settings"
                className={iconButtonClass({
                  size: "sm",
                  pressed: settingsOpen,
                  className: "mt-1.5 rounded-none",
                })}
              >
                <SlidersIcon />
              </Popover.Trigger>
              <Popover.Content
                label="Settings"
                className="left-auto right-0 w-[min(40rem,calc(100vw-2rem))] max-w-none rounded-none"
              >
                {entry && (
                  <CreateSettings
                    kind={bar.kind}
                    models={models.data ?? {}}
                    entry={entry}
                    params={params}
                    onModel={bar.setModel}
                    onParams={(next: Record<string, unknown>) =>
                      bar.setParams(entry.model, next)
                    }
                  />
                )}
              </Popover.Content>
            </Popover.Root>

            <Button
              size="sm"
              className="mt-1.5 inline-flex shrink-0 items-center gap-1.5"
              disabled={!canSend}
              onClick={() => void send()}
            >
              <SendIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
              {busy ? "Sending…" : "Send"}
            </Button>
          </div>

          {!bar.onProject && (
            <div className="border-t border-line px-2 py-1 md:hidden">
              <Combobox
                aria-label="Project"
                options={projectOptions}
                value={target ?? null}
                placeholder="Project"
                onValueChange={(next: string) => bar.setProject(next || null)}
              />
            </div>
          )}

          {active && (
            <div className="flex flex-wrap items-center gap-1 border-t border-line px-2 py-1">
              <TemplatePicker
                compact
                cast={cast.length}
                onPick={bar.setPrompt}
              />

              <Popover.Root open={previewOpen} onOpenChange={setPreviewOpen}>
                <Popover.Trigger
                  className={`inline-flex h-8 items-center gap-1.5 rounded-none px-3 text-sm font-medium ${
                    previewOpen
                      ? "bg-surface-alt text-ink"
                      : "text-muted hover:text-ink"
                  }`}
                >
                  <EyeIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
                  Preview
                </Popover.Trigger>
                <Popover.Content
                  label="Preview"
                  className="w-[min(40rem,calc(100vw-2rem))] max-w-none rounded-none"
                >
                  <PromptPreview
                    prompt={bar.prompt}
                    blocks={templates.data?.blocks ?? {}}
                  />
                </Popover.Content>
              </Popover.Root>

              {unfilled.length > 0 && (
                <Text
                  variant="caption"
                  tone="muted"
                  className="ml-1 hidden md:block"
                >
                  {unfilled.length} unfilled: {unfilled.join(" ")}
                </Text>
              )}

              <Text
                variant="caption"
                tone="muted"
                className="ml-auto font-mono"
              >
                {lines} {lines === 1 ? "line" : "lines"}
              </Text>
            </div>
          )}
        </div>

        {active && entry && (
          <div className="flex flex-col rounded-none border border-t-0 border-line bg-card">
            <CreateModeStrip
              kind={bar.kind}
              entry={entry}
              attachments={attachments}
              role={bar.role}
              onRole={bar.setRole}
              onDetach={bar.detach}
              onClear={bar.clearAttachments}
              keep={bar.keep}
              onKeep={bar.setKeep}
              params={params}
              onParams={(next: Record<string, unknown>) =>
                bar.setParams(entry.model, next)
              }
            />
            {bar.role !== null && target && (
              <CreateDrawer
                projectId={target}
                cast={projectCast}
                attached={new Set(attachments.map((each) => each.ref.node))}
                onAttach={(ref: AttachRef) => {
                  if (bar.role) attach(ref, bar.role);
                }}
                onClose={() => bar.setRole(null)}
              />
            )}
          </div>
        )}

        {held && (
          <Alert.Root intent="warning" className="mt-2 rounded-none">
            <Alert.Title>This request has been run here before</Alert.Title>
            <Alert.Description>
              <span>
                Another run in this project sent exactly this prompt, these
                parameters and these images on {formatDate(held.twin.created)}.
                Sending again bills again — a model answers differently every
                time, so a second attempt is often the point.{" "}
              </span>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button
                  size="sm"
                  disabled={busy}
                  onClick={() => void send(true)}
                >
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
                  onClick={() =>
                    navigate(runPath(held.twin.project, held.twin.id))
                  }
                >
                  Open the earlier run
                </Button>
              </div>
            </Alert.Description>
          </Alert.Root>
        )}

        {failure && (
          <Alert.Root intent="danger" className="mt-2 rounded-none">
            <Alert.Title>Could not send this run</Alert.Title>
            <Alert.Description>{failure}</Alert.Description>
          </Alert.Root>
        )}
      </div>
    </div>
  );
}
