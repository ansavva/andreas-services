import { useCallback, useMemo } from "react";

import { Text } from "@ansavva/design-system";

import { getModelSchema } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import type { ModelEntry } from "../../types";
import { EmptyState } from "../common/EmptyState";
import { LoadError } from "../common/LoadError";
import { SectionLoading } from "../common/SectionLoading";
import { SchemaParams, describedProps } from "../run/SchemaParams";
import { resolveChips } from "./CreateChips";

/**
 * More options: what the chip row does not carry, as the model's own form.
 *
 * **The form is the live schema, minus what has a chip.** `SchemaParams`
 * draws `GET /api/models/<name>/schema` — the same document
 * `services/schema.py` checks the payload against — so what is offered is
 * what the model will accept today; the values it starts from are the
 * snapshot defaults `seedPlan` wrote into the panel's params. Skipped: the
 * prompt (its editor is above), the image fields (those are sends, drawn as
 * tiles, never params — hard rule #3), and every input that already has a
 * chip, so nothing is offered twice. The model itself is not here either: it
 * is the first chip, and the sheet's own row.
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

  const values = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(params).map(([key, value]) => [key, paramText(value)]),
      ),
    [params],
  );

  return (
    <div className="flex flex-col gap-4" data-create-settings="">
      {entry.note && (
        <Text variant="caption" tone="muted">
          {entry.note}
        </Text>
      )}

      {schema.error ? (
        <LoadError
          what="the model's schema"
          message={schema.error}
          onRetry={schema.reload}
        />
      ) : schema.loading || !schema.data ? (
        <SectionLoading label="Loading the model's inputs" />
      ) : describedProps(schema.data, skip).length === 0 ? (
        <EmptyState title="Nothing more to set — the chips carry every input this model takes." />
      ) : (
        <SchemaParams
          schema={schema.data}
          skip={skip}
          values={values}
          onSet={(name, text) => {
            const next = { ...params };
            if (text === null) delete next[name];
            else next[name] = paramValue(text);
            onParams(next);
          }}
        />
      )}
    </div>
  );
}

/** A parameter value as text: a string as itself, anything else as its JSON. */
export function paramText(value: unknown): string {
  if (typeof value === "string") return value;
  return value === undefined ? "" : JSON.stringify(value);
}

/** Text back to a value: JSON if it reads as JSON, the text itself otherwise. */
export function paramValue(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
