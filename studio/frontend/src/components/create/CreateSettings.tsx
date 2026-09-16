import { useCallback, useMemo, useState } from "react";

import { Button, Text } from "@ansavva/design-system";

import { getModelSchema } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import type { ModelEntry } from "../../types";
import { LoadError } from "../common/LoadError";
import { SectionLoading } from "../common/SectionLoading";
import { describedProps } from "../run/SchemaParams";
import {
  ParamRows,
  SettingRows,
  SettingsChoices,
  SettingsPickProvider,
  resolveChips,
  type Picking,
} from "./CreateChips";

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
      ...["prompt", images.refs, images.start, images.end, entry.clips?.source].filter(
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
    // Every input has a chip: nothing below them, rather than a line saying so.
    return null;
  }
  return (
    <div data-create-settings="">
      <SettingRows schema={schema.data} skip={skip} params={params} onParams={onParams} />
    </div>
  );
}

/**
 * The settings panel, whole: the chips as rows, then More options — and one
 * setting's choices in place of both when a listed value is pressed.
 *
 * **One component for the popover and the phone sheet**, because the paging is
 * the same answer to two different clippings: on the phone a menu anchored to a
 * row at the foot of the screen opens off the bottom of it, and on a pointer
 * the panel is a scroll box that cuts a nested menu off — reported as `Output
 * format` losing its last choices. Neither happens to a view that IS the panel.
 * It is also the pattern the sheet already used for the model list.
 */
export function SettingsPanel({
  entry,
  params,
  onParams,
  actions,
}: {
  entry: ModelEntry;
  params: Record<string, unknown>;
  onParams: (next: Record<string, unknown>) => void;
  /**
   * What can be done with the whole set: keep it as this person's starting
   * point for the model, or go back to the model's own. Under the rows on
   * both the popover and the phone sheet, since the sheet is where the
   * settings get tuned by hand and then wanted again next time.
   */
  actions: {
    /** Whether a default of the person's own is in force for this model. */
    saved: boolean;
    onSaveDefault: () => void;
    onReset: () => void;
  } | null;
}) {
  const [picking, setPicking] = useState<Picking | null>(null);

  if (picking) {
    return <SettingsChoices picking={picking} onBack={() => setPicking(null)} />;
  }

  return (
    <SettingsPickProvider onPick={setPicking}>
      <ParamRows entry={entry} params={params} onParams={onParams} />
      <CreateSettings entry={entry} params={params} onParams={onParams} />
      {actions && (
        <div className="mt-3 flex items-center justify-between gap-2 border-t border-line pt-3" data-settings-actions="">
          <Text as="span" variant="caption" tone="muted">
            {actions.saved ? "Starts from your defaults." : "Starts from the model's defaults."}
          </Text>
          <span className="flex shrink-0 items-center gap-1">
            <Button intent="ghost" size="sm" onClick={actions.onReset}>
              Reset
            </Button>
            <Button intent="secondary" size="sm" onClick={actions.onSaveDefault}>
              Set as default
            </Button>
          </span>
        </div>
      )}
    </SettingsPickProvider>
  );
}
