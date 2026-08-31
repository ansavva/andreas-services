import { useCallback, useMemo, useState } from "react";

import { Alert, Badge, Button, Card, Field, Spinner, Text } from "@ansavva/design-system";

import { getReferenceSpec, saveSpecAngle, saveSpecBlock } from "../apis/studio";
import { AutoTextarea } from "../components/common/AutoTextarea";
import { PageBar } from "../components/layout/PageBar";
import { useResource } from "../hooks/useResource";
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
 * Two lists, because there are two row classes and they answer different
 * questions. A **block** is shared prose an angle cites by name; an **angle** is
 * one orientation's template plus the description and tags that get written onto
 * a promoted image. Editing either is one row's write, so two people working on
 * two angles do not overwrite each other — the property the phrasebook gained by
 * becoming rows, for the same reasons.
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

  if (loading) return <Spinner />;
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
          {/*
            **One page, and blocks inline where they are cited.**

            They were two tabs, which made the commonest edit — read a prompt,
            notice a phrase is wrong, fix it — a switch, a hunt and a switch
            back, with the prompt no longer on screen while you changed the
            words it uses. An angle template is mostly citations; the blocks ARE
            most of what it says, so hiding them behind a tab hid most of the
            prompt.
          */}
          <Text tone="muted">
            {data.angles.length} angles. A block is shared prose — expand one to
            read or edit it, and the change reaches every angle citing it.
          </Text>
          <AngleList spec={data} setData={setData} />
        </>
      )}
    </>
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
  const found = prompt.match(/\{[a-z_]+\}/g) ?? [];
  return Array.from(new Set(found.map((token) => token.slice(1, -1))));
}

/** Values the assembler computes rather than reading off a block row. */
const COMPUTED = new Set([
  "top",
  "style",
  "must",
  "build",
  "age",
  "identity_block",
  "identity_slots",
  "angle_slot",
  "torso_slot",
]);

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

  return (
    <div className="rounded border border-line">
      {/*
        Collapsed by default. An angle cites six or seven blocks and expanding
        all of them would bury the template they belong to — the thing the
        reader came for.
      */}
      <button
        type="button"
        onClick={() => setOpen((was) => !was)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
      >
        <span className="font-mono text-sm">{`{${name}}`}</span>
        <span className="flex items-center gap-2">
          {dirty ? <Badge size="sm">unsaved</Badge> : null}
          <Text tone="muted">
            {usedBy === 1 ? "1 angle" : `${usedBy} angles`}
          </Text>
        </span>
      </button>
      {open ? (
        <div className="flex flex-col gap-2 px-3 pb-3">
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
          </div>
        </div>
      ) : (
        <Text tone="muted" className="block truncate px-3 pb-2">
          {text}
        </Text>
      )}
    </div>
  );
}

function AngleList({ spec, setData }: { spec: ReferenceSpec; setData: SetData }) {
  return (
    <>
      {spec.angles.map((angle) => (
        <AngleEditor key={angle.id} angle={angle} spec={spec} setData={setData} />
      ))}
    </>
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
  const unknown = useMemo(
    () => cited.filter((name) => !(name in spec.blocks) && !COMPUTED.has(name)),
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
        angle_image: angle.angle_image,
        torso_image: angle.torso_image,
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
      <Card.Title>
        {angle.id} <Badge size="sm">{angle.group}</Badge>
        {angle.angle_image ? <Badge size="sm">guide</Badge> : null}
      </Card.Title>
      <div className="flex flex-col gap-2">
        <Field.Root name={`prompt-${angle.id}`}>
          <Field.Label>Prompt</Field.Label>
          {/* Monospace, because WHITESPACE IS NOW PART OF THE PROMPT. Blank
              lines survive assembly and reach the model — the best render this
              repo has produced was laid out in paragraphs — so a proportional
              face that hides a doubled space or a trailing one is hiding
              something that is actually sent. */}
          <AutoTextarea
            value={prompt}
            onValueChange={setPrompt}
            className="font-mono"
          />
        </Field.Root>

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
        {/*
          The cited blocks, in place. Reading a prompt without them is reading a
          third of it — a template is mostly citations — and editing one used to
          mean leaving the prompt behind on another tab.
        */}
        {cited.filter((name) => name in spec.blocks).map((name) => (
          <BlockEditor
            key={name}
            name={name}
            text={spec.blocks[name] ?? ""}
            setData={setData}
            usedBy={spec.angles.filter((a) => citations(a.prompt).includes(name)).length}
          />
        ))}
        {cited.some((name) => COMPUTED.has(name)) ? (
          <Text tone="muted">
            Filled from the character:{" "}
            {cited.filter((name) => COMPUTED.has(name)).join(", ")}
          </Text>
        ) : null}
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
          <Field.Description>
            Written onto the image when a run is promoted. Never sent to a model.
          </Field.Description>
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
