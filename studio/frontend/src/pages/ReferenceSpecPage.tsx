import { useCallback, useMemo, useState } from "react";

import { Alert, Badge, Button, Card, Field, Spinner, Tabs, Text } from "@ansavva/design-system";

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
        <Tabs.Root defaultValue="angles">
          <Tabs.List className="overflow-x-auto border-b border-line">
            <Tabs.Tab value="angles">Angles ({data.angles.length})</Tabs.Tab>
            <Tabs.Tab value="blocks">Blocks ({Object.keys(data.blocks).length})</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="angles">
            <AngleList spec={data} setData={setData} />
          </Tabs.Panel>
          <Tabs.Panel value="blocks">
            <BlockList spec={data} setData={setData} />
          </Tabs.Panel>
        </Tabs.Root>
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

function BlockList({ spec, setData }: { spec: ReferenceSpec; setData: SetData }) {
  const names = useMemo(() => Object.keys(spec.blocks).sort(), [spec.blocks]);
  return (
    <>
      {names.map((name) => (
        <BlockEditor key={name} name={name} text={spec.blocks[name] ?? ""} setData={setData} />
      ))}
    </>
  );
}

function BlockEditor({
  name,
  text,
  setData,
}: {
  name: string;
  text: string;
  setData: SetData;
}) {
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
    <Card.Root>
      <Card.Title>{name}</Card.Title>
      <div className="flex flex-col gap-2">
        <Field.Root name={`block-${name}`}>
          <AutoTextarea value={draft} onValueChange={setDraft} />
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
          <Button intent="ghost" onClick={() => setDraft(text)} disabled={saving}>
            Revert
          </Button>
        ) : null}
      </Card.Footer>
    </Card.Root>
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
          <AutoTextarea value={prompt} onValueChange={setPrompt} />
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
        <Text>
          Cites: {cited.length === 0 ? "nothing" : cited.join(", ")}
        </Text>
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
