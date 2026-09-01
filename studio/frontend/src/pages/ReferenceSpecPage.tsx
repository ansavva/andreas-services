import { useCallback, useMemo, useState } from "react";

import {
  Alert,
  Badge,
  Button,
  Card,
  Field,
  Input,
  Tabs,
  Text,
} from "@ansavva/design-system";

import {
  deleteSpecBlock,
  getReferenceSpec,
  saveSpecAngle,
  saveSpecBlock,
} from "../apis/studio";
import { ApertureSpinner } from "../components/common/Aperture";
import { AutoTextarea } from "../components/common/AutoTextarea";
import { ConfirmDeleteButton } from "../components/common/ConfirmDeleteButton";
import { TokenizedPromptEditor } from "../components/common/TokenizedPromptEditor";
import type { PromptToken } from "../components/common/TokenizedPromptEditor";
import { AnglePlate } from "../components/common/AnglePlate";
import { PromptPreview } from "../components/common/PromptPreview";
import { PageBar } from "../components/layout/PageBar";
import { useResource } from "../hooks/useResource";
import { useSearchParamState } from "../hooks/useSearchParamState";
import type { ReferenceSpec, SpecAngle } from "../types";

/**
 * The reference spec: the prose every reference render is assembled from.
 *
 * **This screen is the point of the whole change.** The words lived in
 * `reference_angles.yaml` in the pipeline package, so tuning one — which is the
 * entire nature of this prose, it is written against what a model actually
 * returned — meant a code change, a review and a release. Anyone without a
 * checkout could not read it, let alone fix it.
 *
 * Two tabs, because there are two row classes and they answer different
 * questions. A **block** is shared prose an angle cites by name; an **angle** is
 * one orientation's template plus the description and tags that get written onto
 * a promoted image. Editing either is one row's write, so two people working on
 * two angles do not overwrite each other — the property the phrasebook gained by
 * becoming rows, for the same reasons.
 *
 * **The blocks were inlined under each angle for a while, and are not any more.**
 * The argument for inlining was that a template is mostly citations, so a prompt
 * read without its blocks is a third of a prompt. That argument is now answered
 * by `PromptPreview`, which writes every block out beside the box as you type —
 * so the inline copies were the same prose a second time, pushing the next angle
 * off the screen. Reading is the preview's job; editing is this tab's.
 *
 * **Saving here changes what every future reference render says, and nothing
 * else.** No run is touched: a run records the prompt it was given, so work
 * already drafted or shot keeps the words it was made with. That is deliberate
 * and it is what makes editing safe — but it also means a bad edit is invisible
 * until the next draft, which is why the angle editor shows which blocks each
 * template cites.
 */
export function ReferenceSpecPage() {
  const load = useCallback(() => getReferenceSpec(), []);
  const { data, loading, error, setData } = useResource(["reference-spec"], load);

  if (loading) return <ApertureSpinner />;
  if (error)
    return (
      <Alert.Root intent="danger">
        <Alert.Title>Could not read the reference spec</Alert.Title>
        <Alert.Description>{error}</Alert.Description>
      </Alert.Root>
    );
  if (!data) return null;

  const empty = Object.keys(data.blocks).length === 0 && data.angles.length === 0;

  return (
    <>
      <PageBar crumbs={[{ label: "Reference spec", to: "/reference-spec" }]} />
      {empty ? (
        <Alert.Root intent="info">
          <Alert.Title>This library holds no reference spec</Alert.Title>
          <Alert.Description>
            A turnaround has no angles to shoot until it does. Push one with{" "}
            <code>studio spec push --path &lt;file&gt;</code>.
          </Alert.Description>
        </Alert.Root>
      ) : (
        <>
          <SpecTabs spec={data} setData={setData} />
        </>
      )}
    </>
  );
}

function SpecTabs({ spec, setData }: { spec: ReferenceSpec; setData: SetData }) {
  // A query parameter, not `defaultValue`: a tab with no address cannot be
  // sent to anyone, does not survive a refresh and is not what back goes to.
  const [tab, setTab] = useSearchParamState("tab", "angles");
  const names = useMemo(() => Object.keys(spec.blocks).sort(), [spec.blocks]);

  return (
    <Tabs.Root value={tab} defaultValue="angles" onValueChange={setTab}>
      <Tabs.List className="overflow-x-auto border-b border-line">
        <Tabs.Tab value="angles">Angles ({spec.angles.length})</Tabs.Tab>
        <Tabs.Tab value="blocks">Blocks ({names.length})</Tabs.Tab>
      </Tabs.List>

      <Tabs.Panel value="angles">
        {spec.angles.map((angle) => (
          <AngleEditor key={angle.id} angle={angle} spec={spec} setData={setData} />
        ))}
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
              text={spec.blocks[name] ?? ""}
              setData={setData}
              usedBy={
                spec.angles.filter((a) =>
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
  next: ReferenceSpec | null | ((current: ReferenceSpec | null) => ReferenceSpec | null),
) => void;

/**
 * Which `{placeholders}` a template cites, in the order it cites them.
 *
 * Shown next to every angle because a template naming a block nobody wrote is
 * the failure this screen makes possible: deleting a block is one click, and the
 * angle that cited it does not break until somebody drafts. Listing them turns
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
 * called `angle_slot` won or lost depending on whether the angle bound a plate.
 */
const CHARACTER = ["top", "style", "must", "build", "age", "identity_block"];
//: `angle` and `torso` were the pose plates and are gone — they distorted the
//: thing they existed to record. `anchor` is the sentence a chained shoot
//: carries, empty when there is no anchor.
const SLOT = ["identity", "anchor"];

/** The bare spelling, which still resolves — see the editor's note on `legacy`. */
const LEGACY = new Set([
  ...CHARACTER,
  "identity_slots",
]);

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
      const saved = await saveSpecBlock(name, text);
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
          <Alert.Description>{failed}</Alert.Description>
        </Alert.Root>
      ) : null}
      <div className="flex gap-2">
        <Button
          onClick={create}
          disabled={saving || problem !== null || !name || !text.trim()}
        >
          {saving ? "Creating…" : "Create"}
        </Button>
        <Button intent="ghost" onClick={() => setOpen(false)} disabled={saving}>
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
  /** How many angles cite this block. Shown BEFORE the box, not after a save. */
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
      const saved = await saveSpecBlock(name, draft);
      // The row we just wrote, swapped in — rather than refetching the whole
      // spec to show one paragraph somebody is still reading.
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
      await deleteSpecBlock(name);
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
          <span className="flex shrink-0 items-center gap-2">
            {dirty ? <Badge size="sm">unsaved</Badge> : null}
            <span className="text-xs text-muted">
              {usedBy === 1 ? "1 angle" : `${usedBy} angles`}
            </span>
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
              Shared — editing this changes {usedBy} angles.
            </Text>
          ) : null}
          <Field.Root name={`block-${name}`}>
            <AutoTextarea value={draft} onValueChange={setDraft} className="font-mono" />
          </Field.Root>
          {failed ? (
            <Alert.Root intent="danger">
              <Alert.Description>{failed}</Alert.Description>
            </Alert.Root>
          ) : null}
          <div className="flex gap-2">
            <Button onClick={save} disabled={!dirty || saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
            {dirty ? (
              <Button intent="ghost" onClick={() => setDraft(text)} disabled={saving}>
                Revert
              </Button>
            ) : null}
            {/* Nothing is lost by closing: the draft lives on this component,
                which stays mounted, and the collapsed card carries the
                `unsaved` badge until it is saved or reverted. */}
            <Button intent="ghost" onClick={() => setOpen(false)} disabled={saving}>
              Close
            </Button>
            {/*
              **Nothing checks whether an angle still cites it, and that is the
              route's deliberate position** — a template names its blocks in
              prose, so the only honest check is to assemble every angle and see
              what fails, which the assembly does loudly. What this screen CAN do
              is say the count before the press, because it already knows it.
            */}
            <ConfirmDeleteButton
              noun={usedBy > 0
                ? `{${name}} — ${usedBy} angle(s) cite it and will refuse to draft`
                : `{${name}}`}
              onConfirm={remove}
              disabled={saving}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function AngleEditor({
  angle,
  spec,
  setData,
}: {
  angle: SpecAngle;
  spec: ReferenceSpec;
  setData: SetData;
}) {
  const [prompt, setPrompt] = useState(angle.prompt);
  const [description, setDescription] = useState(angle.description);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const dirty = prompt !== angle.prompt || description !== angle.description;

  const cited = useMemo(() => citations(prompt), [prompt]);
  // What `+` offers: this library's blocks, then the values the assembler fills
  // from the character. Both are placeholders in the template and only one of
  // them is editable, which is why the pill says which it is.
  const promptTokens = useMemo<PromptToken[]>(() => {
    const blocks = Object.entries(spec.blocks).sort(([a], [b]) => a.localeCompare(b));
    return [
      ...blocks.map(([name, text]) => ({
        name: `block.${name}`,
        kind: "block" as const,
        hint: text.slice(0, 60),
      })),
      ...CHARACTER.map((name) => ({ name: `character.${name}`, kind: "computed" as const })),
      ...SLOT.map((name) => ({ name: `slot.${name}`, kind: "computed" as const })),
      // Not offered, still drawn — every template written before the namespaces
      // uses the bare spelling and has to keep looking like what it is.
      ...blocks.map(([name]) => ({ name, kind: "block" as const, legacy: true })),
      ...[...LEGACY].map((name) => ({ name, kind: "computed" as const, legacy: true })),
    ];
  }, [spec.blocks]);
  const unknown = useMemo(
    () =>
      cited.filter((name) => {
        const block = blockNamed(name);
        if (block !== null) return !(block in spec.blocks) && !LEGACY.has(block);
        const [space, member] = name.split(".");
        if (space === "character") return !CHARACTER.includes(member ?? "");
        if (space === "slot") return !SLOT.includes(member ?? "");
        return true;
      }),
    [cited, spec.blocks],
  );

  const save = useCallback(async () => {
    setSaving(true);
    setFailed(null);
    try {
      const saved = await saveSpecAngle(angle.id, {
        group: angle.group,
        prompt,
        description,
        tags: angle.tags,
        order: angle.order,
      });
      setData((current) =>
        current
          ? {
              ...current,
              angles: current.angles.map((a) => (a.id === saved.id ? { ...a, ...saved } : a)),
            }
          : current,
      );
    } catch (problem) {
      setFailed(problem instanceof Error ? problem.message : String(problem));
    } finally {
      setSaving(false);
    }
  }, [angle, description, prompt, setData]);

  return (
    <Card.Root>
      {/* The plate, here too. This screen is where an angle's words are
          actually written, and it showed the id and nothing else — so what the
          orientation MEANS was only visible on the tab you shoot from. */}
      <div className="flex items-start gap-3">
        <AnglePlate path={angle.illustration} name={angle.id} className="w-16 shrink-0" />
        <Card.Title>
          {angle.id} <Badge size="sm">{angle.group}</Badge>
        </Card.Title>
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
          <Field.Root name={`prompt-${angle.id}`}>
            <Field.Label>Prompt</Field.Label>
            {/* A description here as well as on the preview, so both columns'
                headers are the same height and the two boxes line up. */}
            <Field.Description>
              Type {"{"} to insert a placeholder, or write one out in full.
            </Field.Description>
            {/* Pills, not characters. A template is text with named holes, and
                typed by hand a mistyped `{face_onl}` looked exactly like a
                correct one and did not fail until the angle was drafted and
                refused. Typed or taken from the `{` menu, it becomes a pill
                only if it names something.

                The value is still the same plain string — see the editor's own
                note on why the round trip has to be byte-exact. */}
            <TokenizedPromptEditor
              value={prompt}
              onValueChange={setPrompt}
              tokens={promptTokens}
              ariaLabel={`Prompt for ${angle.id}`}
            />
          </Field.Root>
          <PromptPreview prompt={prompt} blocks={spec.blocks} />
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
              {unknown.join(", ")} — drafting this angle will be refused until the
              block exists or the template stops citing it.
            </Alert.Description>
          </Alert.Root>
        ) : null}

        <Field.Root name={`description-${angle.id}`}>
          <Field.Label>Description</Field.Label>
          <AutoTextarea minRows={2} value={description} onValueChange={setDescription} />
        </Field.Root>

        {failed ? <Alert.Root intent="danger">
            <Alert.Description>{failed}</Alert.Description>
          </Alert.Root> : null}
      </div>
      <Card.Footer>
        <Button onClick={save} disabled={!dirty || saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
        {dirty ? (
          <Button
            intent="ghost"
            onClick={() => {
              setPrompt(angle.prompt);
              setDescription(angle.description);
            }}
            disabled={saving}
          >
            Revert
          </Button>
        ) : null}
      </Card.Footer>
    </Card.Root>
  );
}
