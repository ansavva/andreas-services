import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  Alert,
  Button,
  Field,
  Input,
  Tabs,
  Text,
} from "@ansavva/design-system";

import {
  deleteBlock,
  deleteTemplate,
  newTemplateId,
  getTemplates,
  saveTemplate,
  saveBlock,
} from "../apis/studio";
import { AutoTextarea } from "../components/common/AutoTextarea";
import { ConfirmDeleteButton } from "../components/common/ConfirmDeleteButton";
import { ConfirmDestroyDialog } from "../components/common/ConfirmDestroyDialog";
import { FormBar } from "../components/common/FormBar";
import { EmptyState } from "../components/common/EmptyState";
import { EntityRow } from "../components/entity/EntityRow";
import {
  ChevronLeftIcon,
  PlusIcon,
  TemplateIcon,
} from "../components/common/icons";
import { CITE_TEXT } from "../components/common/citeStyle";
import { LoadError } from "../components/common/LoadError";
import { PageLoading } from "../components/common/PageLoading";
import { TagSelect } from "../components/common/TagSelect";
import { TokenizedPromptEditor } from "../components/common/TokenizedPromptEditor";
import type { PromptToken } from "../components/common/TokenizedPromptEditor";
import { PromptPreview } from "../components/common/PromptPreview";
import { PageBar } from "../components/layout/PageBar";
import { useResource } from "../hooks/useResource";
import { useSearchParamState } from "../hooks/useSearchParamState";
import type { TemplateLibrary, PromptTemplate } from "../types";
import { blockNamed, citationsIn } from "../utils/citations";

/**
 * The template library: the prose every prompt is assembled from.
 *
 * **This screen is the point of the whole change.** The words lived in
 * `reference_angles.yaml` in the pipeline package, so tuning one — which is the
 * entire nature of this prose, it is written against what a model actually
 * returned — meant a code change, a review and a release. Anyone without a
 * checkout could not read it, let alone fix it.
 *
 * Two tabs, because there are two row classes and they answer different
 * questions. A **block** is shared prose a template cites by name; a **template** is
 * one orientation's template plus the description and tags that get written onto
 * a promoted image. Editing either is one row's write, so two people working on
 * two templates do not overwrite each other — the property the phrasebook gained by
 * becoming rows, for the same reasons.
 *
 * **The blocks were inlined under each template for a while, and are not any more.**
 * The argument for inlining was that a template is mostly citations, so a prompt
 * read without its blocks is a third of a prompt. That argument is now answered
 * by `PromptPreview`, which writes every block out beside the box as you type —
 * so the inline copies were the same prose a second time, pushing the next template
 * off the screen. Reading is the preview's job; editing is this tab's.
 *
 * **Saving here changes what every future reference render says, and nothing
 * else.** No run is touched: a run records the prompt it was given, so work
 * already drafted or shot keeps the words it was made with. That is deliberate
 * and it is what makes editing safe — but it also means a bad edit is invisible
 * until the next draft, which is why the template editor shows which blocks each
 * template cites.
 */
export function TemplatesPage() {
  const navigate = useNavigate();
  const load = useCallback(() => getTemplates(), []);
  const { data, loading, error, reload, setData } = useResource(
    ["templates"],
    load,
  );

  // Which tab is active decides what "New" makes — lifted here, out of
  // `LibraryTabs`, because the button that makes one now lives in the page's
  // own header rather than as a tile inside the list it fills.
  const [tab, setTab] = useSearchParamState("tab", "templates");
  const [creatingTemplate, setCreatingTemplate] = useState(false);
  const [creatingBlock, setCreatingBlock] = useState(false);

  if (loading) return <PageLoading label="Loading templates" />;
  if (error)
    return (
      <LoadError
        what="the templates"
        message={error}
        onRetry={reload}
        escape={{ label: "Back to home", onClick: () => navigate("/") }}
      />
    );
  if (!data) return null;

  // The count in the bar, not repeated as a section heading under it — see
  // `CharactersPage` for the reasoning. Whichever tab is open, because that
  // is the count the page is actually showing.
  const blockCount = Object.keys(data.blocks).length;
  const shownCount = tab === "blocks" ? blockCount : data.templates.length;
  const shownNoun = tab === "blocks" ? "block" : "template";

  return (
    <>
      {/* No crumb — this is a top-level screen. */}
      <PageBar
        title="Templates"
        meta={
          <Text variant="caption" family="mono" tone="muted">
            {shownCount} {shownCount === 1 ? shownNoun : `${shownNoun}s`}
          </Text>
        }
        primary={
          <Button
            size="sm"
            onClick={() =>
              tab === "blocks"
                ? setCreatingBlock(true)
                : setCreatingTemplate(true)
            }
          >
            <PlusIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
            {tab === "blocks" ? "New block" : "New template"}
          </Button>
        }
      />

      <LibraryTabs
        library={data}
        setData={setData}
        tab={tab}
        setTab={setTab}
        creatingTemplate={creatingTemplate}
        setCreatingTemplate={setCreatingTemplate}
        creatingBlock={creatingBlock}
        setCreatingBlock={setCreatingBlock}
      />
    </>
  );
}

type SetData = (
  next:
    | TemplateLibrary
    | null
    | ((current: TemplateLibrary | null) => TemplateLibrary | null),
) => void;

function LibraryTabs({
  library,
  setData,
  tab,
  setTab,
  creatingTemplate,
  setCreatingTemplate,
  creatingBlock,
  setCreatingBlock,
}: {
  library: TemplateLibrary;
  setData: SetData;
  tab: string;
  setTab: (next: string) => void;
  creatingTemplate: boolean;
  setCreatingTemplate: (next: boolean) => void;
  creatingBlock: boolean;
  setCreatingBlock: (next: boolean) => void;
}) {
  const names = useMemo(
    () => Object.keys(library.blocks).sort(),
    [library.blocks],
  );
  // Which template is open, in the address like every other "which one" in
  // the app — so a reload and a shared link land on the same editor.
  const [openId, setOpenId] = useSearchParamState("template", "");
  const opened = library.templates.find((each) => each.id === openId) ?? null;
  // The open block, the same way: its name is its identity.
  const [openName, setOpenBlock] = useSearchParamState("block", "");
  const openedBlock = openName in library.blocks ? openName : null;
  const citedBy = useCallback(
    (name: string) =>
      library.templates.filter((a) =>
        citations(a.prompt).some((c) => blockNamed(c) === name),
      ).length,
    [library.templates],
  );

  return (
    <Tabs.Root value={tab} defaultValue="templates" onValueChange={setTab}>
      <Tabs.List className="overflow-x-auto border-b border-line">
        <Tabs.Tab value="templates">Templates</Tabs.Tab>
        <Tabs.Tab value="blocks">Blocks</Tabs.Tab>
      </Tabs.List>

      <Tabs.Panel value="templates" className="flex flex-col gap-3 pt-3">
        {creatingTemplate && (
          <NewTemplateForm
            onCreated={(saved) => {
              setData((current) =>
                current
                  ? { ...current, templates: [...current.templates, saved] }
                  : current,
              );
              setCreatingTemplate(false);
            }}
            onCancel={() => setCreatingTemplate(false)}
          />
        )}

        {!creatingTemplate && library.templates.length === 0 && (
          <EmptyState
            title="No templates yet."
            hint={
              <>
                A run has no prompt to start from until there are. Write one
                here, or push several at once with{" "}
                <code>studio templates push --path &lt;file&gt;</code>.
              </>
            }
            action={
              <Button size="sm" onClick={() => setCreatingTemplate(true)}>
                <PlusIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
                New template
              </Button>
            }
          />
        )}

        {/* A list first, like every other listing: one row per template by
            name, and the editor only for the one that is open. Fourteen open
            editors stacked was fourteen screens to find one.

            The rows are `EntityRow`, drawn as every other list draws them —
            flush, ruled, no gap, an icon where a scene has its thumbnail —
            rather than the spaced mono rows they were, which looked like
            nothing else in the app. The tags trail in mono, not as badges:
            five badges on every row was a row of chrome with a name in it,
            and a tag is a value here rather than a status. */}
        {!creatingTemplate &&
          opened === null &&
          library.templates.length > 0 && (
            <div className="flex flex-col" aria-label="Templates">
              {library.templates.map((template) => (
                <EntityRow
                  key={template.id}
                  title={template.name}
                  subtitle={firstLine(template.prompt)}
                  thumb={{
                    icon: (
                      <TemplateIcon className="size-5 shrink-0 fill-none stroke-muted stroke-[1.5]" />
                    ),
                  }}
                  onOpen={() => setOpenId(template.id)}
                  trailing={
                    template.tags.length > 0 ? (
                      <Text
                        variant="caption"
                        family="mono"
                        tone="muted"
                        className="max-md:hidden"
                      >
                        {template.tags.join(" · ")}
                      </Text>
                    ) : undefined
                  }
                />
              ))}
            </div>
          )}

        {!creatingTemplate && opened !== null && (
          <>
            <div>
              <Button
                size="sm"
                intent="secondary"
                onClick={() => setOpenId("")}
              >
                <ChevronLeftIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
                All templates
              </Button>
            </div>
            <TemplateEditor
              key={opened.id}
              template={opened}
              library={library}
              setData={setData}
            />
          </>
        )}
      </Tabs.Panel>

      <Tabs.Panel value="blocks" className="flex flex-col gap-3 pt-3">
        {creatingBlock && (
          <NewBlockForm
            taken={names}
            onCreated={(saved) => {
              setData((current) =>
                current
                  ? {
                      ...current,
                      blocks: {
                        ...current.blocks,
                        [saved.name]: saved.text,
                      },
                    }
                  : current,
              );
              setCreatingBlock(false);
            }}
            onCancel={() => setCreatingBlock(false)}
          />
        )}

        {!creatingBlock && names.length === 0 && (
          <EmptyState
            title="No blocks yet."
            hint="A block is shared prose a template cites by name — add one to give a template something to point at."
            action={
              <Button size="sm" onClick={() => setCreatingBlock(true)}>
                <PlusIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
                New block
              </Button>
            }
          />
        )}

        {/* The same shape as the Templates tab, and as every list in the app:
            one ruled row per block, the editor only for the one that is open.
            It was a grid of collapsible cards showing six lines of each — a
            third shape of list on a page that already had two, and the one
            screen in the app where a name did not open a page. A row says
            how many templates cite it, because that is what a person needs
            to know before opening one to edit. */}
        {!creatingBlock && openedBlock === null && names.length > 0 && (
          <div className="flex flex-col" aria-label="Blocks">
            {names.map((name) => (
              <EntityRow
                key={name}
                title={`@block.${name}`}
                mono
                subtitle={firstLine(library.blocks[name] ?? "")}
                thumb={{
                  icon: (
                    <TemplateIcon className="size-5 shrink-0 fill-none stroke-muted stroke-[1.5]" />
                  ),
                }}
                onOpen={() => setOpenBlock(name)}
                trailing={
                  <Text variant="caption" family="mono" tone="muted">
                    {citedBy(name) === 1 ? "1 template" : `${citedBy(name)} templates`}
                  </Text>
                }
              />
            ))}
          </div>
        )}

        {!creatingBlock && openedBlock !== null && (
          <>
            <div>
              <Button
                size="sm"
                intent="secondary"
                onClick={() => setOpenBlock("")}
              >
                <ChevronLeftIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
                All blocks
              </Button>
            </div>
            <BlockEditor
              key={openedBlock}
              name={openedBlock}
              text={library.blocks[openedBlock] ?? ""}
              setData={setData}
              usedBy={citedBy(openedBlock)}
              onDeleted={() => setOpenBlock("")}
            />
          </>
        )}
      </Tabs.Panel>
    </Tabs.Root>
  );
}

/**
 * Which `@citations` a template makes, each once, in the order it makes them.
 *
 * Shown next to every template because one naming a block nobody wrote is
 * the failure this screen makes possible: deleting a block is one click, and the
 * template that cited it does not break until somebody drafts. Listing them turns
 * that into something visible now rather than a refusal later.
 */
function citations(prompt: string): string[] {
  return Array.from(new Set(citationsIn(prompt).map((each) => each.name)));
}

/** The first line of a prompt — what a row shows of it. */
function firstLine(prompt: string): string {
  return prompt.trim().split("\n")[0] ?? "";
}

/**
 * What a template may cite, by namespace.
 *
 * **Three sources, and they are edited in three different places** — which is
 * the whole reason the dotted spelling exists. A bare name said nothing about
 * where to go and change it, and worse, two of them could answer to the same
 * word: a block called `top` lost to the character's bible every time, and one
 * called `angle_slot` won or lost depending on whether the template bound a plate.
 */
/**
 * What `@character.N.…` may cite, positionally.
 *
 * **`build` and `must` name a VARIANT.** The bible answers both differently for
 * a face than for a body — a face crops at mid-chest, so the proportions below
 * it are noise — and citing the bare name is refused rather than defaulted,
 * because a face template silently filled with body proportions is wrong in a
 * way the finished prose does not show.
 *
 * **How many positions to offer.** A template is written before anybody knows
 * which run will use it, so there is no cast to count — three is what a
 * multi-character prompt has ever needed, and a fourth is typed by hand.
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
const POSITIONS = [1, 2, 3];

//: `angle` and `torso` were the pose plates and are gone — they distorted the
//: thing they existed to record. `anchor` went with the chaining it described.
const SLOT = ["identity"];

/**
 * Write a block that does not exist yet.
 *
 * `PATCH` on a name nothing holds creates it — the route is an overwrite rather
 * than a claim, because a block IS its name and saving an edit to one is the
 * whole point of it. So creating and editing are the same call, and this is a
 * form rather than a second route.
 *
 * **The name rule is the citation rule.** A block is cited as `@block.<name>`
 * and a citation ends where a name does, so a name that is not an identifier
 * is a block nothing can ever name. The API refuses one; saying so here means
 * finding out while typing rather than on save.
 *
 * **Controlled by the caller now.** This used to open its own dashed tile and
 * hold its own `open` state; the tile is gone and "New block" lives in the
 * page's own header, above the list it fills, so mounting this form at all
 * IS the open state.
 */
function NewBlockForm({
  taken,
  onCreated,
  onCancel,
}: {
  taken: string[];
  onCreated: (saved: { name: string; text: string }) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const problem = !name
    ? null
    : !/^[a-z_][a-z0-9_]*$/.test(name)
      ? "Lowercase letters, digits and underscores, starting with a letter."
      : taken.includes(name)
        ? "A block already holds that name — open it to edit the words."
        : null;

  const create = useCallback(async () => {
    setSaving(true);
    setFailed(null);
    try {
      const saved = await saveBlock(name, text);
      onCreated(saved);
    } catch (bad) {
      setFailed(bad instanceof Error ? bad.message : String(bad));
    } finally {
      setSaving(false);
    }
  }, [name, onCreated, text]);

  return (
    <div className="flex flex-col gap-2 border border-line p-3">
      <Field.Root name="new-block-name" invalid={problem !== null}>
        <Field.Label>Name</Field.Label>
        <Field.Description>
          Cited as{" "}
          <span className={`font-mono ${CITE_TEXT.block}`}>
            @block.{name || "name"}
          </span>
          .
        </Field.Description>
        <Input value={name} onValueChange={setName} className="font-mono" />
        {problem ? <Field.Error>{problem}</Field.Error> : null}
      </Field.Root>
      <Field.Root name="new-block-text">
        <Field.Label>Text</Field.Label>
        <AutoTextarea
          value={text}
          onValueChange={setText}
          className="font-mono"
        />
      </Field.Root>
      {failed ? (
        <Alert.Root intent="danger">
          <Alert.Title>Could not create the block</Alert.Title>
          <Alert.Description>{failed}</Alert.Description>
        </Alert.Root>
      ) : null}
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={() => void create()}
          disabled={saving || problem !== null || !name || !text.trim()}
        >
          {saving ? "Creating…" : "Create"}
        </Button>
        <Button
          intent="secondary"
          size="sm"
          onClick={onCancel}
          disabled={saving}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}

function BlockEditor({
  name,
  text,
  setData,
  usedBy,
  onDeleted,
}: {
  name: string;
  text: string;
  setData: SetData;
  /** How many templates cite this block. Shown BEFORE the box, not after a save. */
  usedBy: number;
  /** The row is gone, so the editor has nothing to show — back to the list. */
  onDeleted: () => void;
}) {
  const [draft, setDraft] = useState(text);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const dirty = draft !== text;

  const save = useCallback(async () => {
    setSaving(true);
    setFailed(null);
    try {
      const saved = await saveBlock(name, draft);
      // The row we just wrote, swapped in — rather than refetching the whole
      // library to show one paragraph somebody is still reading.
      setData((current) =>
        current
          ? { ...current, blocks: { ...current.blocks, [name]: saved.text } }
          : current,
      );
    } catch (problem) {
      setFailed(problem instanceof Error ? problem.message : String(problem));
    } finally {
      setSaving(false);
    }
  }, [draft, name, setData]);

  // Its own message, not `failed`: that one sits under the save row with the
  // save's title, and a delete that was refused is not a save that was.
  const [removeFailed, setRemoveFailed] = useState<string | null>(null);

  const remove = useCallback(async () => {
    setSaving(true);
    setRemoveFailed(null);
    try {
      await deleteBlock(name);
      setData((current) => {
        if (!current) return current;
        const blocks = { ...current.blocks };
        delete blocks[name];
        return { ...current, blocks };
      });
      onDeleted();
    } catch (problem) {
      setRemoveFailed(
        problem instanceof Error ? problem.message : String(problem),
      );
      setSaving(false);
    }
  }, [name, onDeleted, setData]);

  return (
    // The same frame the template editor draws: the name and the delete in a
    // header row, the form under it, the save bar at the foot.
    <div className="flex flex-col gap-3 border border-line p-4">
      <div className="flex items-start justify-between gap-3">
        {/* In the block hue: the name here is the thing a violet pill in
            a template points at, and the same colour says so. The count is
            not repeated under it — the row said it, and the line under the
            header says it again where it matters, before the box. */}
        <Text variant="title" family="mono" className={CITE_TEXT.block}>
          @block.{name}
        </Text>
        {/*
          **Nothing checks whether a template still cites it, and that is the
          route's deliberate position** — a template names its blocks in
          prose, so the only honest check is to assemble every template and see
          what fails, which the assembly does loudly. What this screen CAN do
          is weigh the confirmation by the count, because it already knows it:
          a block nothing cites is one thing and arms in place; a cited one
          takes templates down with it and types its name, like any other
          entity with children.
        */}
        {usedBy > 0 ? (
          <ConfirmDestroyDialog
            label="Delete"
            disabled={saving}
            title={`Delete @block.${name}?`}
            summary={`${usedBy === 1 ? "1 template cites it" : `${usedBy} templates cite it`} and will refuse to draft until edited. Nothing checks that for you.`}
            confirmWord={name}
            onConfirm={remove}
          />
        ) : (
          <ConfirmDeleteButton
            noun={`@block.${name}`}
            onConfirm={remove}
            disabled={saving}
          />
        )}
      </div>

      {removeFailed ? (
        <Alert.Root intent="danger" onDismiss={() => setRemoveFailed(null)}>
          <Alert.Title>Could not delete the block</Alert.Title>
          <Alert.Description>{removeFailed}</Alert.Description>
        </Alert.Root>
      ) : null}

      {/* Said before the edit, not after it. A block reads as local until
          you know it is not, and a shared edit noticed on save is noticed
          too late. */}
      <Text tone="muted">
        {usedBy === 0
          ? "Nothing cites this yet."
          : usedBy === 1
            ? "1 template cites this."
            : `Shared — editing this changes ${usedBy} templates.`}
      </Text>
      <Field.Root name={`block-${name}`}>
        <Field.Label>Text</Field.Label>
        <AutoTextarea
          value={draft}
          onValueChange={setDraft}
          className="font-mono"
        />
      </Field.Root>
      <FormBar
        dirty={dirty}
        saving={saving}
        onSave={() => void save()}
        onRevert={() => setDraft(text)}
        error={failed}
        errorTitle="Could not save the block"
      />
    </div>
  );
}

/**
 * Write a template that does not exist yet.
 *
 * **The page could edit and delete and not create**, which made the library
 * something only `studio templates push` could add to — so writing a new prompt
 * meant a YAML file and a CLI, for prose whose whole nature is that it is tuned
 * in front of the thing it produces.
 *
 * **A name is all it asks for.** The id is minted here and never shown: it is
 * the row's address, not something a person has to invent — asking for one
 * alongside a name was asking the same question twice, and the answer people
 * gave was the name with underscores in it.
 *
 * **Controlled by the caller**, same reasoning as `NewBlockForm`: "New
 * template" is a header button now, not a tile at the foot of the list.
 */
function NewTemplateForm({
  onCreated,
  onCancel,
}: {
  onCreated: (saved: PromptTemplate) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const create = useCallback(async () => {
    setSaving(true);
    setFailed(null);
    try {
      const saved = await saveTemplate(newTemplateId(), {
        name,
        // A prompt is required by the route, so a new one starts as the thing
        // every template here has in common rather than as an empty box the
        // save would refuse.
        prompt: "@block.quality",
        description: "What the image this makes shows.",
        tags: ["untagged"],
      });
      onCreated(saved);
    } catch (problem_) {
      setFailed(
        problem_ instanceof Error ? problem_.message : String(problem_),
      );
    } finally {
      setSaving(false);
    }
  }, [name, onCreated]);

  return (
    <div className="flex flex-col gap-2 border border-line p-3">
      <Field.Root name="new-template-name">
        <Field.Label>Name</Field.Label>
        <Field.Description>What you will pick it by.</Field.Description>
        <Input value={name} onValueChange={setName} />
      </Field.Root>
      {failed ? (
        <Alert.Root intent="danger">
          <Alert.Title>Could not create the template</Alert.Title>
          <Alert.Description>{failed}</Alert.Description>
        </Alert.Root>
      ) : null}
      <div className="flex gap-2">
        <Button
          size="sm"
          disabled={!name.trim() || saving}
          onClick={() => void create()}
        >
          {saving ? "Creating…" : "Create"}
        </Button>
        <Button
          size="sm"
          intent="secondary"
          disabled={saving}
          onClick={onCancel}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}

function TemplateEditor({
  template,
  library,
  setData,
}: {
  template: PromptTemplate;
  library: TemplateLibrary;
  setData: SetData;
}) {
  const [prompt, setPrompt] = useState(template.prompt);
  /**
   * **Editable, which they were not.**
   *
   * The editor saved `prompt` and `description` and passed `name` and `tags`
   * straight back through, so the only way to rename a template or change what
   * its output gets tagged was a YAML file and `studio templates push`. Both are
   * things a person changes while looking at the prompt they belong to.
   */
  const [name, setName] = useState(template.name ?? "");
  const [tags, setTags] = useState<string[]>(template.tags ?? []);
  const [description, setDescription] = useState(template.description);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  // **All four fields.** It watched the prompt and the description only, so
  // editing the name or the tags left Save disabled and the edit unsavable —
  // the box accepted typing and then threw it away on the next read.
  const dirty =
    prompt !== template.prompt ||
    description !== template.description ||
    name !== template.name ||
    tags.join(" ") !== (template.tags ?? []).join(" ");

  const cited = useMemo(() => citations(prompt), [prompt]);
  // What `+` offers: this library's blocks, then the values the assembler fills
  // from the character. Both are placeholders in the template and only one of
  // them is editable, which is why the pill says which it is.
  const promptTokens = useMemo<PromptToken[]>(() => {
    const blocks = Object.entries(library.blocks).sort(([a], [b]) =>
      a.localeCompare(b),
    );
    return [
      ...blocks.map(([name, text]) => ({
        name: `block.${name}`,
        kind: "block" as const,
        hint: text.slice(0, 60),
      })),
      ...POSITIONS.flatMap((at) =>
        CHARACTER_FIELDS.map((field) => ({
          name: `character.${at}.${field}`,
          kind: "computed" as const,
          hint: `character ${at}`,
        })),
      ),
      ...SLOT.map((name) => ({
        name: `slot.${name}`,
        kind: "computed" as const,
      })),
    ];
  }, [library.blocks]);
  const unknown = useMemo(
    () =>
      cited.filter((name) => {
        const block = blockNamed(name);
        if (block !== null) return !(block in library.blocks);
        const [space, ...rest] = name.split(".");
        if (space === "character") {
          // `@character.N.…` — the position first, then the field, which
          // may itself name a variant (`build.face`). A bare `@character.top`
          // has no position and is exactly what the fill refuses, so it lands
          // here as unknown, which is the right answer.
          const [at, ...field] = rest;
          if (!/^\d+$/.test(at ?? "")) return true;
          return !CHARACTER_FIELDS.includes(field.join("."));
        }
        if (space === "slot") return !SLOT.includes(rest.join(".") || "");
        return true;
      }),
    [cited, library.blocks],
  );

  const save = useCallback(async () => {
    setSaving(true);
    setFailed(null);
    try {
      // Addressed by its id, so a rename is just a field in the body.
      const saved = await saveTemplate(template.id, {
        name,
        prompt,
        description,
        tags,
      });
      setData((current) =>
        current
          ? {
              ...current,
              templates: current.templates.map((each) =>
                each.id === template.id ? { ...each, ...saved } : each,
              ),
            }
          : current,
      );
    } catch (problem) {
      setFailed(problem instanceof Error ? problem.message : String(problem));
    } finally {
      setSaving(false);
    }
  }, [template, description, name, prompt, tags, setData]);

  return (
    <div className="flex flex-col gap-3 border border-line p-4">
      {/* **No plate.** A template used to carry an `illustration` — a picture
          of the orientation it shot — because every template WAS an orientation
          of a standard set. A template is any prompt somebody wrote now, and
          most will never have such a picture; a field that only fourteen rows
          could fill is a field that reads as missing on everything else. */}
      <div className="flex items-start gap-3">
        <div className="flex flex-1 flex-col gap-2">
          <Text variant="title">{name || template.name}</Text>
          <div className="grid gap-2 sm:grid-cols-2">
            <Field.Root name={`template-name-${template.id}`}>
              <Field.Label>Name</Field.Label>
              <Field.Description>What a person picks it by.</Field.Description>
              <Input value={name} onValueChange={setName} />
            </Field.Root>
            <Field.Root name={`template-tags-${template.id}`}>
              <Field.Label>Tags</Field.Label>
              <Field.Description>
                What its output is tagged with when it is promoted. Templates
                keep their own list — a file&rsquo;s tags are a different
                vocabulary.
              </Field.Description>
              <TagSelect
                scope="template"
                value={tags}
                onChange={setTags}
                manage
              />
            </Field.Root>
          </div>
        </div>
        {/* A template is prose somebody wrote, so it can be thrown away like
            one. Nothing cites a template at all — a run copies its words — so
            unlike a block there is no count to warn about. */}
        <ConfirmDeleteButton
          noun={template.name}
          disabled={saving}
          onConfirm={async () => {
            await deleteTemplate(template.id);
            setData((current) =>
              current
                ? {
                    ...current,
                    templates: current.templates.filter(
                      (each) => each.id !== template.id,
                    ),
                  }
                : current,
            );
          }}
        />
      </div>
      <div className="flex flex-col gap-2">
        {/*
          **Side by side once there is room for it.** A template is mostly
          citations, so the box shows a third of what the prompt says and the
          rest is collapsed further down the page — judging an edit meant
          expanding a block, reading it, collapsing it and assembling the whole
          thing in your head. Below `lg` they stack, because two narrow columns
          of monospace are worse than one.
        */}
        <div className="grid gap-3 lg:grid-cols-2">
          <Field.Root name={`prompt-${template.id}`}>
            <Field.Label>Prompt</Field.Label>
            {/* A description here as well as on the preview, so both columns'
                headers are the same height and the two boxes line up. */}
            <Field.Description>
              Type @ to cite a block or a character, or write one out in full.
            </Field.Description>
            {/* Pills, not characters. A template is text with named holes, and
                typed by hand a mistyped `@block.face_onl` looked exactly like
                a correct one and did not fail until the template was drafted
                and refused. Typed or taken from the `@` menu, it becomes a
                pill only if it names something.

                The value is still the same plain string — see the editor's own
                note on why the round trip has to be byte-exact.

                `cite-wash`: the blurred wash of the three citation hues, under
                the prose. This box is the one place the chrome has a colour,
                and `styles/app.css` says why it is this one. */}
            <TokenizedPromptEditor
              value={prompt}
              onValueChange={setPrompt}
              tokens={promptTokens}
              ariaLabel={`Prompt for ${template.name}`}
              className="cite-wash rounded-md border border-line p-3"
            />
          </Field.Root>
          <PromptPreview prompt={prompt} blocks={library.blocks} />
        </div>

        {/*
          A template citing a block nobody wrote does not break until somebody
          drafts. Naming the unknown ones turns a later refusal into something
          visible while it is still being typed.

          **In words, not in colour.** A Badge in this package is deliberately
          neutral chrome with an intent DOT rather than a coloured pill —
          `badge.props` records why, and says in the same breath that colour is
          never the only carrier of the meaning because the badge's own text
          says what it is. A red-vs-grey pill would have carried this warning on
          hue alone, which is exactly the thing that note rules out.
        */}
        {unknown.length > 0 ? (
          <Alert.Root intent="warning">
            <Alert.Title>
              No block provides{" "}
              {unknown.length === 1 ? "this name" : "these names"}
            </Alert.Title>
            <Alert.Description>
              {unknown.join(", ")} — drafting this template will be refused
              until the block exists or the template stops citing it.
            </Alert.Description>
          </Alert.Root>
        ) : null}

        <Field.Root name={`description-${template.id}`}>
          <Field.Label>Description</Field.Label>
          <AutoTextarea
            minRows={2}
            value={description}
            onValueChange={setDescription}
          />
        </Field.Root>
      </div>
      <FormBar
        dirty={dirty}
        saving={saving}
        onSave={() => void save()}
        onRevert={() => {
          setPrompt(template.prompt);
          setDescription(template.description);
          setName(template.name);
          setTags(template.tags ?? []);
        }}
        error={failed}
        errorTitle="Could not save the template"
      />
    </div>
  );
}
