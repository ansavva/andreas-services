import { useCallback, useMemo } from "react";

import { getModelSchema } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import type { ModelEntry } from "../../types";
import { EmptyState } from "../common/EmptyState";
import { LoadError } from "../common/LoadError";
import { SectionLoading } from "../common/SectionLoading";
import { describedProps } from "../run/SchemaParams";
import { SettingRows, resolveChips } from "./CreateChips";

/**
 * More options: what the chip row does not carry, as rows.
 *
 * **The rows are the live schema, minus what has a chip.** `GET
 * /api/models/<name>/schema` is the same document `services/schema.py`
 * checks the payload against, so what is offered is what the model will
 * accept today; the values start from the snapshot defaults `seedPlan` wrote
 * into the panel's params. Skipped: the prompt (its editor is above), the
 * image fields (sends, drawn as tiles, never params — hard rule #3), every
 * input that already has a chip, and the model itself — the first chip, and
 * the sheet's own row.
 *
 * **Rows, the way the phone sheet draws them, not a form.** This used to be
 * `SchemaParams` — a label, the mono key, a full-width control and the
 * schema's description under each — which is the run page's payload editor
 * and reads as one. ElevenLabs gives every setting the same line: the word,
 * then the control; the description is a hover away.
 *
 * No cost here. The registry entry carries no price, and a number invented
 * from a model's typical run time would be a claim this app cannot back.
 */
export function CreateSettings({
  entry,
  params,
  onParams,
}: {
  entry: ModelEntry;
  params: Record<string, unknown>;
  onParams: (next: Record<string, unknown>) => void;
}) {
  const model = entry.model;
  const schema = useResource(
    ["model-schema", model],
    useCallback(() => getModelSchema(model), [model]),
  );

  const skip = useMemo(() => {
    const images = entry.images ?? {};
    return new Set([
      ...["prompt", images.refs, images.start, images.end].filter(
        (key): key is string => typeof key === "string",
      ),
      ...resolveChips(entry, schema.data ?? null).map((chip) => chip.name),
    ]);
  }, [entry, schema.data]);

  if (schema.error) {
    return (
      <LoadError
        what="the model's schema"
        message={schema.error}
        onRetry={schema.reload}
      />
    );
  }
  if (schema.loading || !schema.data) {
    return <SectionLoading label="Loading the model's inputs" />;
  }
  if (describedProps(schema.data, skip).length === 0) {
    return (
      <EmptyState title="Nothing more to set — the chips carry every input this model takes." />
    );
  }
  return (
    <div data-create-settings="">
      <SettingRows schema={schema.data} skip={skip} params={params} onParams={onParams} />
    </div>
  );
}
