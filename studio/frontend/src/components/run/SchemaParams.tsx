import { Button, Field, Input, Select, Switch, Text } from "@ansavva/design-system";

import type { ModelSchema, SchemaProp } from "../../types";
import { AutoTextarea } from "../common/AutoTextarea";

/**
 * The model's own inputs, as a form.
 *
 * **The schema drawn here is the schema that refuses at submit.** Parameters
 * were a list of typed key/value pairs, so getting `aspect_ratio` right meant
 * knowing that this model spells it `16:9`, the next one `1024x1024` and a third
 * `match_input_image` — and finding out was a 400 arriving after the plan had
 * been written and the approval given. `GET /api/models/<name>/schema` is a live
 * provider read and `services/schema.py` checks the payload against the same
 * document, so what is offered here is what the model will accept today.
 *
 * **What is NOT drawn is as deliberate as what is.**
 *
 * - `prompt` has its own editor above, and two boxes for one field is a way to
 *   save the wrong one.
 * - Anything **uri-shaped** is a SEND, not a parameter. Hard rule #3: an image
 *   reaches a model as a short-lived presigned URL minted from a node studio
 *   already holds, so a text box here would invite pasting the other kind of
 *   URL — which `runs.py` refuses, after the typing.
 * - A prop whose shape has no control here is left to the freeform rows rather
 *   than approximated. A form that guessed at an object or a nested array would
 *   be a second, worse opinion about a schema this app does not own.
 *
 * **A prop nobody set is not written.** Absent and "the default, written down"
 * are different records: `params` is inside the digest an approval names, so
 * filling every default in would turn "the model chose" into "a person chose"
 * on the one document that is supposed to say which.
 */

/** Which control a prop gets. `null` means: this form cannot draw it. */
type ParamKind = "enum" | "number" | "boolean" | "string";

/** The param values as the editor holds them — text, keyed by prop name. */
type ParamValues = Record<string, string | undefined>;

/**
 * An input's allowed values, following a `$ref` when the enum is indirect.
 *
 * **The enums are where the indirection is**, which is why this exists rather
 * than reading `spec.enum` and stopping: Replicate emits `aspect_ratio` as an
 * `allOf` naming a component, and a form that did not follow it would put a free
 * text box in front of exactly the fields most worth a list. Mirrors
 * `services/schema.py:enum_of`, which is what will judge the answer.
 */
export function enumOf(
  spec: SchemaProp,
  schemas: Record<string, SchemaProp>,
): unknown[] | null {
  if (Array.isArray(spec.enum) && spec.enum.length > 0) return spec.enum;
  const allOf = Array.isArray(spec.allOf) ? (spec.allOf as SchemaProp[]) : [];
  for (const sub of allOf) {
    if (!sub || typeof sub !== "object") continue;
    if (Array.isArray(sub.enum) && sub.enum.length > 0) return sub.enum;
    const ref = typeof sub.$ref === "string" ? sub.$ref : "";
    // The last segment, rather than a fixed `#/components/schemas/` prefix: the
    // API hands back the sibling components under their own names and nothing
    // guarantees the pointer keeps that spelling.
    const target = ref ? schemas[ref.split("/").pop() ?? ""] : undefined;
    if (target && Array.isArray(target.enum) && target.enum.length > 0)
      return target.enum;
  }
  return null;
}

/** A prop that carries an image — a send, never a param. See hard rule #3. */
export function isUriShaped(spec: SchemaProp): boolean {
  if (spec.type === "string" && spec.format === "uri") return true;
  if (spec.type === "array") {
    const items = spec.items as SchemaProp | undefined;
    return items?.type === "string" && items.format === "uri";
  }
  return false;
}

function kindOf(
  spec: SchemaProp,
  schemas: Record<string, SchemaProp>,
): ParamKind | null {
  if (isUriShaped(spec)) return null;
  if (enumOf(spec, schemas)) return "enum";
  if (spec.type === "integer" || spec.type === "number") return "number";
  if (spec.type === "boolean") return "boolean";
  if (spec.type === "string") return "string";
  return null;
}

/** Where the provider wants this input to sit. Unordered props sink. */
function order(spec: SchemaProp): number {
  const at = spec["x-order"];
  return typeof at === "number" ? at : Number.MAX_SAFE_INTEGER;
}

/**
 * The props this form draws, in the provider's own order.
 *
 * `sort` is stable, so props sharing an `x-order` — or carrying none — keep the
 * order the schema listed them in.
 */
/**
 * A provider credential, which this form must never offer a box for.
 *
 * Several models take an optional key of their own — `openai_api_key` on the
 * GPT Image entries — and drawing it is worse than useless: a plan is a
 * RECORD. It is written to the catalog, rebuilt into the payload, hashed into
 * the approval digest and rendered back on the run page, so a key typed here
 * would be a secret stored in a row and shown to everyone who can read the run.
 * Studio's provider credential lives on the API and nowhere else.
 *
 * Matched on the name because that is what the schema gives us — nothing in
 * the JSON marks a field as secret.
 */
function isCredential(name: string): boolean {
  return /api[_-]?key|token|secret|password|credential/i.test(name);
}

export function describedProps(
  schema: ModelSchema,
  skip: ReadonlySet<string>,
): Array<{ name: string; spec: SchemaProp; kind: ParamKind }> {
  const schemas = schema.schemas ?? {};
  return Object.entries(schema.props ?? {})
    .filter(([name]) => name !== "prompt" && !skip.has(name) && !isCredential(name))
    .map(([name, spec]) => ({ name, spec, kind: kindOf(spec, schemas) }))
    .filter((each): each is { name: string; spec: SchemaProp; kind: ParamKind } =>
      each.kind !== null,
    )
    .sort((a, b) => order(a.spec) - order(b.spec));
}

/** The keys the typed form owns — what the freeform rows below must not repeat. */
export function describedKeys(
  schema: ModelSchema | null,
  skip: ReadonlySet<string>,
): ReadonlySet<string> {
  if (!schema) return new Set();
  return new Set(describedProps(schema, skip).map((each) => each.name));
}

export function SchemaParams({
  schema,
  skip,
  values,
  onSet,
}: {
  schema: ModelSchema;
  /** Fields that are sends, or have an editor of their own. */
  skip: ReadonlySet<string>;
  values: ParamValues;
  /** `null` clears the prop back to unset, which writes nothing. */
  onSet: (name: string, text: string | null) => void;
}) {
  const shown = describedProps(schema, skip);
  if (shown.length === 0) return null;

  return (
    <div className="flex flex-col gap-3">
      {shown.map(({ name, spec, kind }) => (
        <Param
          key={name}
          name={name}
          spec={spec}
          kind={kind}
          schemas={schema.schemas ?? {}}
          value={values[name]}
          onSet={onSet}
        />
      ))}
    </div>
  );
}

/** The description, the model's default and the range, as one line. */
function hintOf(spec: SchemaProp): string {
  const low = typeof spec.minimum === "number" ? spec.minimum : null;
  const high = typeof spec.maximum === "number" ? spec.maximum : null;
  return [
    typeof spec.description === "string" ? spec.description : null,
    spec.default === undefined
      ? null
      : `Model default: ${JSON.stringify(spec.default)}`,
    low === null && high === null
      ? null
      : `Range ${low ?? "any"} to ${high ?? "any"}`,
  ]
    .filter(Boolean)
    .join(" · ");
}

function Param({
  name,
  spec,
  kind,
  schemas,
  value,
  onSet,
}: {
  name: string;
  spec: SchemaProp;
  kind: ParamKind;
  schemas: Record<string, SchemaProp>;
  value: string | undefined;
  onSet: (name: string, text: string | null) => void;
}) {
  const hint = hintOf(spec);
  const set = (text: string) => onSet(name, text === "" ? null : text);

  /**
   * Long text gets a growing box — decided from the SCHEMA and never from what
   * is in the field.
   *
   * Deciding it from the value would swap `Input` for `AutoTextarea` under a
   * cursor as somebody typed past the threshold, which unmounts the element they
   * are typing into.
   */
  const multiline =
    kind === "string" &&
    (spec.format === "textarea" ||
      (typeof spec.default === "string" && spec.default.length > 60));

  return (
    <Field.Root name={`param_${name}`}>
      <Field.Label>{name}</Field.Label>

      {kind === "enum" ? (
        <Select
          options={[
            // Blank is not a value the model takes; it is how a person says
            // "leave this out", which is the only way to get the default back.
            { value: "", label: "model default" },
            ...(enumOf(spec, schemas) ?? []).map((option) => ({
              value: String(option),
              label: String(option),
            })),
          ]}
          value={value ?? ""}
          onValueChange={set}
        />
      ) : kind === "boolean" ? (
        // A switch has two positions and this prop has three states, so the
        // third is a control of its own rather than a position on the switch:
        // off must not double as unset, or every boolean the schema mentions
        // would be written into the plan the moment the form rendered.
        <div className="flex flex-wrap items-center gap-2">
          <Switch.Root
            aria-label={name}
            checked={value === "true"}
            onCheckedChange={(on: boolean) => onSet(name, on ? "true" : "false")}
          >
            <Switch.Thumb />
          </Switch.Root>
          <Text variant="caption" tone="muted">
            {value === undefined ? "model default" : value === "true" ? "on" : "off"}
          </Text>
          {value !== undefined && (
            <Button
              intent="secondary"
              size="sm"
              onClick={() => onSet(name, null)}
            >
              Use the model default
            </Button>
          )}
        </div>
      ) : kind === "number" ? (
        <Input
          type="number"
          value={value ?? ""}
          placeholder="model default"
          min={typeof spec.minimum === "number" ? spec.minimum : undefined}
          max={typeof spec.maximum === "number" ? spec.maximum : undefined}
          onValueChange={set}
        />
      ) : multiline ? (
        <AutoTextarea
          value={value ?? ""}
          placeholder="model default"
          onValueChange={set}
        />
      ) : (
        <Input
          value={value ?? ""}
          placeholder="model default"
          onValueChange={set}
        />
      )}

      {hint !== "" && <Field.Description>{hint}</Field.Description>}
    </Field.Root>
  );
}
