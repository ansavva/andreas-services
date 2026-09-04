import { useCallback, useMemo } from "react";

import { Field, Select, Text } from "@ansavva/design-system";

import { getModelSchema } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import type { ModelEntry, RunKind } from "../../types";
import { LoadError } from "../common/LoadError";
import { SectionLoading } from "../common/SectionLoading";
import { SchemaParams } from "../run/SchemaParams";

/**
 * The parameters behind the sliders icon: which model, and what it takes.
 *
 * **The model list is the kind's.** A video model offered under an image run
 * is a 400 at submit, after the plan has been written, so the switch on the
 * bar filters this list and switching it picks that kind's default.
 *
 * **The form is the live schema, seeded from the snapshot.** `SchemaParams`
 * draws `GET /api/models/<name>/schema` — the same document
 * `services/schema.py` checks the payload against — so what is offered is
 * what the model will accept today; the values it starts from are the
 * snapshot defaults `seedPlan` wrote into the bar's params. The image fields
 * are skipped: those are sends, drawn on the strip, never params (hard rule
 * #3).
 *
 * No cost here. The registry entry carries no price, and a number invented
 * from a model's typical run time would be a claim this app cannot back.
 */
export function CreateSettings({
  kind,
  models,
  entry,
  params,
  onModel,
  onParams,
}: {
  kind: RunKind;
  models: Record<string, ModelEntry>;
  entry: ModelEntry;
  params: Record<string, unknown>;
  /** The Replicate `owner/name` of the chosen model. */
  onModel: (model: string) => void;
  onParams: (next: Record<string, unknown>) => void;
}) {
  const offered = useMemo(
    () =>
      Object.values(models)
        .filter((each) => each.kind === kind)
        .sort((a, b) => a.key.localeCompare(b.key)),
    [kind, models],
  );

  const model = entry.model;
  const schema = useResource(
    ["model-schema", model],
    useCallback(() => getModelSchema(model), [model]),
  );

  const skip = useMemo(() => {
    const images = entry.images ?? {};
    return new Set(
      ["prompt", images.refs, images.start, images.end].filter(
        (key): key is string => typeof key === "string",
      ),
    );
  }, [entry.images]);

  const values = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(params).map(([key, value]) => [key, paramText(value)]),
      ),
    [params],
  );

  return (
    <div className="flex flex-col gap-4" data-create-settings="">
      <Field.Root name="model">
        <Field.Label>Model</Field.Label>
        {/* Labelled by the registry key, which is what the skills and the CLI
            call it. The Replicate id is what gets sent. */}
        <Select
          options={offered.map((each) => ({
            value: each.model,
            label: each.key,
          }))}
          value={model}
          onValueChange={onModel}
        />
      </Field.Root>

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
