import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  Alert,
  Button,
  Card,
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
import { FormBar } from "../components/common/FormBar";
import { EmptyState } from "../components/common/EmptyState";
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
  const { data, loading, error, reload, setData } = useResource(["templates"], load);

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

  const empty = Object.keys(data.blocks).length === 0 && data.templates.length === 0;

  return (
    <>
      <PageBar crumbs={[{ label: "Templates", to: "/templates" }]} />
      {empty ? (
        <EmptyState
          title="No templates yet."
          hint={
            <>
              A run has no prompt to start from until there are. Push some with{" "}
              <code>studio templates push --path &lt;file&gt;</code>.
            </>
          }
        />
      ) : (
        <>
          <LibraryTabs library={data} setData={setData} />
        </>
      )}
    </>
  );
}

function LibraryTabs({ library, setData }: { library: TemplateLibrary; setData: SetData }) {
  // A query parameter, not `defaultValue`: a tab with no address cannot be
  // sent to anyone, does not survive a refresh and is not what back goes to.
  const [tab, setTab] = useSearchParamState("tab", "templates");
  const names = useMemo(() => Object.keys(library.blocks).sort(), [library.blocks]);

  return (
    <Tabs.Root value={tab} defaultValue="templates" onValueChange={setTab}>
      <Tabs.List className="overflow-x-auto border-b border-line">
        <Tabs.Tab value="templates">Templates ({library.templates.length})</Tabs.Tab>
        <Tabs.Tab value="blocks">Blocks ({names.length})</Tabs.Tab>
      </Tabs.List>

      <Tabs.Panel value="templates">
        {library.templates.map((template) => (
          <TemplateEditor key={template.id} template={template} library={library} setData={setData} />
        ))}
        <NewTemplate setData={setData} />
      </Tabs.Panel>

      <Tabs.Panel value="blocks">
        {/*
          **A grid, and the prose is the content.** These were full-width rows
          carrying one truncated line each, so eighteen blocks were eighteen
          screens of chrome and almost none of the words — on a tab whose entire
          job is showing the words. Narrower columns fit more lines of each and
          more blocks at once; an opened one takes the full width, because
          editing a paragraph in a third of a screen is the opposite problem.
        */}
        <div className="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
          <NewBlock taken={names} setData={setData} />
          {names.map((name) => (
            <BlockEditor
              key={name}
              name={name}
              text={library.blocks[name] ?? ""}
              setData={setData}
              usedBy={
                library.templates.filter((a) =>
                  citations(a.prompt).some((c) => blockNamed(c) === name),
                ).length
              }
            />
          ))}
        </div>
      </Tabs.Panel>
    </Tabs.Root>
  );
}

type SetData = (
  next: TemplateLibrary | null | ((current: TemplateLibrary | null) => TemplateLibrary | null),
) => void;

/**
 * Which `{placeholders}` a template cites, in the order it cites them.
 *
 * Shown next to every template because one naming a block nobody wrote is
 * the failure this screen makes possible: deleting a block is one click, and the
 * template that cited it does not break until somebody drafts. Listing them turns
 * that into something visible now rather than a refusal later.
 */
function citations(prompt: string): string[] {
  const found = prompt.match(/\{[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*\}/g) ?? [];
  return Array.from(new Set(found.map((token) => token.slice(1, -1))));
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
 * What `{character.N.…}` may cite, positionally.
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
  "top", "style", "age", "identity_block",
  "build.face", "build.body", "must.face", "must.body",
];
const POSITIONS = [1, 2, 3];

//: `angle` and `torso` were the pose plates and are gone — they distorted the
//: thing they existed to record. `anchor` went with the chaining it described.
const SLOT = ["identity"];

/** The block a citation names, whichever way it is spelled. */
function blockNamed(cited: string): string | null {
  if (cited.startsWith("block.")) return cited.slice(6);
  return cited.includes(".") ? null : cited;
}

/**
 * Write a block that does not exist yet.
 *
 * `PATCH` on a name nothing holds creates it — the route is an overwrite rather
 * than a claim, because a block IS its name and saving an edit to one is the
 * whole point of it. So creating and editing are the same call, and this is a
 * form rather than a second route.
 *
 * **The name rule is the citation rule.** A block is cited as `{block.<name>}`
 * and a dot in a format field is attribute access, so a name that is not an
 * identifier is a block nothing can ever name. The API refuses one; saying so
 * here means finding out while typing rather than on save.
 */
function NewBlock({ taken, setData }: { taken: string[]; setData: SetData }) {
  const [open, setOpen] = useState(false);
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
      setData((current) =>
        current ? { ...current, blocks: { ...current.blocks, [name]: saved.text } } : current,
      );
      setName("");
      setText("");
      setOpen(false);
    } catch (bad) {
      setFailed(bad instanceof Error ? bad.message : String(bad));
    } finally {
      setSaving(false);
    }
  }, [name, setData, text]);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex h-full min-h-24 items-center justify-center rounded border border-dashed border-line px-2 py-1.5 text-sm text-muted hover:bg-surface-alt"
      >
        + New block
      </button>
    );
  }

  return (
    <div className="flex h-full flex-col gap-2 rounded border border-line p-2 md:col-span-full">
      <Field.Root name="new-block-name" invalid={problem !== null}>
        <Field.Label>Name</Field.Label>
        <Field.Description>Cited as {`{block.${name || "name"}}`}.</Field.Description>
        <Input value={name} onValueChange={setName} className="font-mono" />
        {problem ? <Field.Error>{problem}</Field.Error> : null}
      </Field.Root>
      <Field.Root name="new-block-text">
        <Field.Label>Text</Field.Label>
        <AutoTextarea value={text} onValueChange={setText} className="font-mono" />
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
          onClick={create}
          disabled={saving || problem !== null || !name || !text.trim()}
        >
          {saving ? "Creating…" : "Create"}
        </Button>
        <Button intent="secondary" size="sm" onClick={() => setOpen(false)} disabled={saving}>
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
}: {
  name: string;
  text: string;
  setData: SetData;
  /** How many templates cite this block. Shown BEFORE the box, not after a save. */
  usedBy: number;
}) {
  const [open, setOpen] = useState(false);
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
        current ? { ...current, blocks: { ...current.blocks, [name]: saved.text } } : current,
      );
    } catch (problem) {
      setFailed(problem instanceof Error ? problem.message : String(problem));
    } finally {
      setSaving(false);
    }
  }, [draft, name, setData]);

  const remove = useCallback(async () => {
    setSaving(true);
    setFailed(null);
    try {
      await deleteBlock(name);
      setData((current) => {
        if (!current) return current;
        const blocks = { ...current.blocks };
        delete blocks[name];
        return { ...current, blocks };
      });
    } catch (problem) {
      setFailed(problem instanceof Error ? problem.message : String(problem));
      setSaving(false);
    }
  }, [name, setData]);

  return (
    // `h-full`, and no `items-start` on the grid: the cells in a row are as tall
    // as the tallest, so a one-line block beside a paragraph leaves a hole
    // rather than a short box. Ragged bottoms read as a layout fault.
    <div className={`flex h-full flex-col rounded border border-line ${open ? "md:col-span-full" : ""}`}>
      {/*
        Collapsed by default, and collapsed still SHOWS the prose — six lines of
        it rather than one truncated line. A block is a paragraph and the
        question this tab answers is what it says; a name and an ellipsis
        answered nothing and took a full row to do it.
      */}
      <button
        type="button"
        onClick={() => setOpen((was) => !was)}
        aria-expanded={open}
        className="flex w-full flex-col gap-1 px-2 py-1.5 text-left"
      >
        <span className="flex w-full items-center justify-between gap-2">
          <span className="font-mono text-sm">{`{${name}}`}</span>
          <span className="shrink-0 text-xs text-muted">
            {usedBy === 1 ? "1 template" : `${usedBy} templates`}
          </span>
        </span>
        {open ? null : (
          <span className="line-clamp-6 text-xs whitespace-pre-wrap text-muted">{text}</span>
        )}
      </button>
      {open ? (
        <div
          className="flex flex-col gap-2 px-2 pb-2"
          // Escape closes, which is what a person tries first in a box that
          // opened over the thing they were reading. The header toggles too,
          // and did before this — but a header that gives no sign it is a
          // control is a way out only for whoever wrote it.
          onKeyDown={(event) => {
            if (event.key === "Escape") setOpen(false);
          }}
        >
          {/* Said before the edit, not after it. A block reads as local until
              you know it is not, and a shared edit noticed on save is noticed
              too late. */}
          {usedBy > 1 ? (
            <Text tone="muted">
              Shared — editing this changes {usedBy} templates.
            </Text>
          ) : null}
          <Field.Root name={`block-${name}`}>
            <AutoTextarea value={draft} onValueChange={setDraft} className="font-mono" />
          </Field.Root>
          {/* Close is kept off the save row: it shuts the expander, not the
              form. Nothing is lost by closing — the draft lives on this
              component, which stays mounted, until it is saved or reverted. */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button intent="secondary" size="sm" onClick={() => setOpen(false)} disabled={saving}>
              Close
            </Button>
            {/*
              **Nothing checks whether a template still cites it, and that is the
              route's deliberate position** — a template names its blocks in
              prose, so the only honest check is to assemble every template and see
              what fails, which the assembly does loudly. What this screen CAN do
              is say the count before the press, because it already knows it.
            */}
            <ConfirmDeleteButton
              noun={usedBy > 0
                ? `{${name}} — ${usedBy} template(s) cite it and will refuse to draft`
                : `{${name}}`}
              onConfirm={remove}
              disabled={saving}
            />
          </div>
          <FormBar
            dirty={dirty}
            saving={saving}
            onSave={() => void save()}
            onRevert={() => setDraft(text)}
            error={failed}
            errorTitle="Could not save the block"
          />
        </div>
      ) : null}
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
 */
function NewTemplate({ setData }: { setData: SetData }) {
  const [open, setOpen] = useState(false);
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
        prompt: "{block.quality}",
        description: "What the image this makes shows.",
        tags: ["untagged"],
      });
      setData((current) =>
        current ? { ...current, templates: [...current.templates, saved] } : current,
      );
      setOpen(false);
      setName("");
    } catch (problem_) {
      setFailed(problem_ instanceof Error ? problem_.message : String(problem_));
    } finally {
      setSaving(false);
    }
  }, [name, setData]);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex min-h-16 w-full items-center justify-center rounded border border-dashed border-line px-2 py-1.5 text-sm text-muted hover:bg-surface-alt"
      >
        + New template
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded border border-line p-3">
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
        <Button size="sm" disabled={!name.trim() || saving} onClick={() => void create()}>
          {saving ? "Creating…" : "Create"}
        </Button>
        <Button size="sm" intent="secondary" disabled={saving} onClick={() => setOpen(false)}>
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
    tags.join("\u0000") !== (template.tags ?? []).join("\u0000");

  const cited = useMemo(() => citations(prompt), [prompt]);
  // What `+` offers: this library's blocks, then the values the assembler fills
  // from the character. Both are placeholders in the template and only one of
  // them is editable, which is why the pill says which it is.
  const promptTokens = useMemo<PromptToken[]>(() => {
    const blocks = Object.entries(library.blocks).sort(([a], [b]) => a.localeCompare(b));
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
      ...SLOT.map((name) => ({ name: `slot.${name}`, kind: "computed" as const })),
      // Not offered, still drawn — every template written before the namespaces
      // uses the bare spelling and has to keep looking like what it is.
      ...blocks.map(([name]) => ({ name, kind: "block" as const, legacy: true })),
    ];
  }, [library.blocks]);
  const unknown = useMemo(
    () =>
      cited.filter((name) => {
        const block = blockNamed(name);
        if (block !== null) return !(block in library.blocks);
        const [space, ...rest] = name.split(".");
        if (space === "character") {
          // `{character.N.<field>}` — the position first, then the field, which
          // may itself name a variant (`build.face`). A bare `{character.top}`
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
    <Card.Root>
      {/* **No plate.** A template used to carry an `illustration` — a picture
          of the orientation it shot — because every template WAS an orientation
          of a standard set. A template is any prompt somebody wrote now, and
          most will never have such a picture; a field that only fourteen rows
          could fill is a field that reads as missing on everything else. */}
      <div className="flex items-start gap-3">
        <div className="flex flex-1 flex-col gap-2">
          <Card.Title>
            {name || template.name}
          </Card.Title>
          <div className="grid gap-2 sm:grid-cols-2">
            <Field.Root name={`template-name-${template.id}`}>
              <Field.Label>Name</Field.Label>
              <Field.Description>What a person picks it by.</Field.Description>
              <Input value={name} onValueChange={setName} />
            </Field.Root>
            <Field.Root name={`template-tags-${template.id}`}>
              <Field.Label>Tags</Field.Label>
              <Field.Description>
                What its output is tagged with when it is promoted. Templates keep
                their own list — a file&rsquo;s tags are a different vocabulary.
              </Field.Description>
              <TagSelect scope="template" value={tags} onChange={setTags} manage />
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
                    templates: current.templates.filter((each) => each.id !== template.id),
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
          thing in your head. Below `xl` they stack, because two narrow columns
          of monospace are worse than one.
        */}
        <div className="grid gap-3 xl:grid-cols-2">
          <Field.Root name={`prompt-${template.id}`}>
            <Field.Label>Prompt</Field.Label>
            {/* A description here as well as on the preview, so both columns'
                headers are the same height and the two boxes line up. */}
            <Field.Description>
              Type {"{"} to insert a placeholder, or write one out in full.
            </Field.Description>
            {/* Pills, not characters. A template is text with named holes, and
                typed by hand a mistyped `{face_onl}` looked exactly like a
                correct one and did not fail until the template was drafted and
                refused. Typed or taken from the `{` menu, it becomes a pill
                only if it names something.

                The value is still the same plain string — see the editor's own
                note on why the round trip has to be byte-exact. */}
            <TokenizedPromptEditor
              value={prompt}
              onValueChange={setPrompt}
              tokens={promptTokens}
              ariaLabel={`Prompt for ${template.name}`}
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
              No block provides {unknown.length === 1 ? "this name" : "these names"}
            </Alert.Title>
            <Alert.Description>
              {unknown.join(", ")} — drafting this template will be refused until the
              block exists or the template stops citing it.
            </Alert.Description>
          </Alert.Root>
        ) : null}

        <Field.Root name={`description-${template.id}`}>
          <Field.Label>Description</Field.Label>
          <AutoTextarea minRows={2} value={description} onValueChange={setDescription} />
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
    </Card.Root>
  );
}
