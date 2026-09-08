import { useCallback, useMemo, useState, type ReactElement } from "react";

import { Button, Dropdown, Input, Popover, Text } from "@ansavva/design-system";

import { getModelSchema } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import type { ModelEntry, ModelSchema, RunKind, SchemaProp, SnapshotProp } from "../../types";
import { humaniseKey } from "../../utils/format";
import {
  AspectIcon,
  CheckIcon,
  ChevronDownIcon,
  ClockIcon,
  DiamondIcon,
  LayersIcon,
  ModelIcon,
  ResolutionIcon,
  SoundOffIcon,
  SoundOnIcon,
} from "../common/icons";
import { EmptyState } from "../common/EmptyState";
import { describedProps, enumOf } from "../run/SchemaParams";

/**
 * The chip row under the prompt: the model, then the handful of settings a
 * person changes on most runs, each a glyph and a value that opens a short
 * menu — ElevenLabs' `▭ 16:9 · ⤢ 720p · ◷ 4s · 🔊 On`.
 *
 * **Which settings get a chip is a fixed list, and the list is short on
 * purpose.** Every model's full schema is behind the sliders icon; a chip is
 * for the six things worth a press without opening it. The list is matched
 * by NAME against the model's inputs, so a model that has no `duration` draws
 * no duration chip, and a model that spells it `duration_seconds` still gets
 * one. Anything the list does not name stays in the form.
 *
 * **Values come from the model, twice.** The registry snapshot (`entry.snapshot`)
 * is on the entry already and draws the chips the instant a model is chosen;
 * the live schema (`GET /api/models/<name>/schema`) replaces it once it lands,
 * because the live document is what `services/schema.py` will judge the
 * payload against. In tests the live read is refused and the snapshot alone
 * draws.
 *
 * **A chip shows the model's default while nothing is set, and writes only
 * on a choice.** `params` is inside the fingerprint, so a chip that wrote
 * every default on render would turn "the model chose" into "a person chose"
 * — the same rule `SchemaParams` keeps. `Default` at the top of the menu is
 * how a value is unset again.
 */
interface ChipSpec {
  /** The input names this chip stands for, in preference order. */
  names: readonly string[];
  label: string;
  icon: (props: { className?: string }) => ReactElement;
  /** How a value reads on the chip. */
  format?: (value: unknown) => string;
  boolean?: boolean;
}

const CHIP_SPECS: readonly ChipSpec[] = [
  { names: ["aspect_ratio"], label: "Aspect ratio", icon: AspectIcon },
  { names: ["resolution", "size"], label: "Resolution", icon: ResolutionIcon },
  {
    names: ["duration", "duration_seconds"],
    label: "Duration",
    icon: ClockIcon,
    format: (value) => `${String(value)}s`,
  },
  { names: ["quality"], label: "Quality", icon: DiamondIcon },
  {
    names: ["number_of_images", "num_outputs", "num_images", "n"],
    label: "Outputs",
    icon: LayersIcon,
  },
  {
    names: ["generate_audio", "audio"],
    label: "Audio",
    icon: SoundOnIcon,
    boolean: true,
  },
];

const GLYPH = "size-4 shrink-0 fill-none stroke-current stroke-[1.5]";

/** The look every chip in the row shares: a glyph and a value, no box. */
export const chipClass =
  "inline-flex h-8 shrink-0 cursor-pointer items-center gap-1.5 rounded-sm bg-transparent px-2 text-sm font-medium " +
  "text-muted transition-colors hover:bg-fill hover:text-ink " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fill-active";

/**
 * Which way a chip's menu opens. UP from the chip row, which sits at the
 * bottom of the viewport; DOWN from a row in the phone sheet, where the
 * sheet's own scroll would clip anything hung above it.
 */
const MENU_SIDE = { up: "bottom-full top-auto mb-1 mt-0", down: "" } as const;
const MENU_UP = MENU_SIDE.up;

/** One resolved chip: which input it binds, and what it may be. */
export interface ResolvedChip {
  spec: ChipSpec;
  name: string;
  /** The values on offer, or null for a boolean. */
  choices: unknown[] | null;
  modelDefault: unknown;
}

/**
 * Which of the six chips this model has, from the live schema when it is
 * here and the snapshot until then.
 */
export function resolveChips(
  entry: ModelEntry,
  schema: ModelSchema | null,
): ResolvedChip[] {
  const out: ResolvedChip[] = [];
  for (const spec of CHIP_SPECS) {
    for (const name of spec.names) {
      const live = schema?.props?.[name];
      const snap = snapshotProp(entry, name);
      if (!live && !snap) continue;
      if (spec.boolean) {
        out.push({
          spec,
          name,
          choices: null,
          modelDefault: live?.default ?? snap?.default,
        });
        break;
      }
      const choices = live
        ? choicesOf(live, schema?.schemas ?? {})
        : snap
          ? snapshotChoices(snap)
          : null;
      if (!choices || choices.length === 0) continue;
      out.push({ spec, name, choices, modelDefault: live?.default ?? snap?.default });
      break;
    }
  }
  return out;
}

function snapshotProp(entry: ModelEntry, name: string): SnapshotProp | null {
  const prop = entry.snapshot?.[name];
  return prop && typeof prop === "object" ? prop : null;
}

/** The values a live prop allows: its enum, or the whole numbers in its range. */
function choicesOf(spec: SchemaProp, schemas: Record<string, SchemaProp>): unknown[] | null {
  const listed = enumOf(spec, schemas);
  if (listed) return listed;
  if (spec.type === "integer" || spec.type === "number") return rangeChoices(spec);
  return null;
}

function snapshotChoices(prop: SnapshotProp): unknown[] | null {
  if (Array.isArray(prop.enum) && prop.enum.length > 0) return prop.enum;
  if (typeof prop.minimum === "number" || typeof prop.maximum === "number")
    return rangeChoices(prop);
  return null;
}

/**
 * The whole numbers between a prop's bounds, floored at one — a provider
 * that advertises `-1` means "auto", which a chip has no word for. Capped at
 * twenty: a menu longer than that is a form, and the form is a press away.
 */
export function rangeChoices(prop: { minimum?: number; maximum?: number }): number[] {
  const low = Math.max(1, typeof prop.minimum === "number" ? Math.ceil(prop.minimum) : 1);
  const high = typeof prop.maximum === "number" ? Math.floor(prop.maximum) : low + 9;
  if (high - low > 20) return [];
  const out: number[] = [];
  for (let each = low; each <= high; each += 1) out.push(each);
  return out;
}

/**
 * The live schema for a model, or null while it loads or when the read is
 * refused. The chips fall back to the snapshot in both cases.
 */
export function useLiveSchema(model: string): ModelSchema | null {
  const schema = useResource(
    ["model-schema", model],
    useCallback(() => getModelSchema(model), [model]),
  );
  return schema.data ?? null;
}

/** The chips, in the row, for one model. */
export function ParamChipRow({
  entry,
  params,
  onParams,
  className = "flex",
}: {
  entry: ModelEntry;
  params: Record<string, unknown>;
  onParams: (next: Record<string, unknown>) => void;
  /** Carries the display: the row decides when the chips are drawn at all. */
  className?: string;
}) {
  const schema = useLiveSchema(entry.model);
  const chips = useMemo(() => resolveChips(entry, schema), [entry, schema]);
  if (chips.length === 0) return null;

  return (
    <div className={`min-w-0 items-center gap-0.5 ${className}`} data-param-chips="">
      {chips.map((chip) => (
        <ParamChip
          key={chip.name}
          chip={chip}
          value={params[chip.name]}
          onChange={(next) => {
            const out = { ...params };
            if (next === undefined) delete out[chip.name];
            else out[chip.name] = next;
            onParams(out);
          }}
        />
      ))}
    </div>
  );
}

/** One chip. A boolean flips on press; anything else opens its menu. */
export function ParamChip({
  chip,
  value,
  onChange,
  menuSide = "up",
}: {
  chip: ResolvedChip;
  value: unknown;
  /** `undefined` unsets — back to the model's own default. */
  onChange: (next: unknown) => void;
  menuSide?: keyof typeof MENU_SIDE;
}) {
  const { spec } = chip;
  const shown = value === undefined ? chip.modelDefault : value;
  const format = spec.format ?? ((each: unknown) => String(each));

  if (spec.boolean) {
    const on = shown === true;
    const Icon = on ? SoundOnIcon : SoundOffIcon;
    return (
      <Button
        intent="secondary"
        size="sm"
        role="switch"
        aria-checked={on}
        aria-label={spec.label}
        title={`${spec.label}: ${on ? "on" : "off"}`}
        className={chipClass}
        onClick={() => onChange(!on)}
      >
        <Icon className={GLYPH} />
        {on ? "On" : "Off"}
      </Button>
    );
  }

  const Icon = spec.icon;
  const text = shown === undefined || shown === null ? "Auto" : format(shown);
  return (
    <Dropdown.Root>
      <Dropdown.Trigger
        aria-label={`${spec.label}: ${text}`}
        title={spec.label}
        className={chipClass}
      >
        <Icon className={GLYPH} />
        {text}
      </Dropdown.Trigger>
      <Dropdown.Content className={`${MENU_SIDE[menuSide]} right-0 left-auto max-h-80 overflow-y-auto`}>
        <Dropdown.Label>{spec.label}</Dropdown.Label>
        <MenuItem
          on={value === undefined}
          onSelect={() => onChange(undefined)}
        >
          Default
          {chip.modelDefault !== undefined && chip.modelDefault !== null && (
            <span className="ml-1 text-muted">· {format(chip.modelDefault)}</span>
          )}
        </MenuItem>
        {(chip.choices ?? []).map((choice) => (
          <MenuItem
            key={String(choice)}
            on={value !== undefined && String(value) === String(choice)}
            onSelect={() => onChange(choice)}
          >
            {format(choice)}
          </MenuItem>
        ))}
      </Dropdown.Content>
    </Dropdown.Root>
  );
}

/** A menu row with the check on the right, the way a native menu draws it. */
function MenuItem({
  on,
  onSelect,
  children,
}: {
  on: boolean;
  onSelect: () => void;
  children: React.ReactNode;
}) {
  return (
    <Dropdown.Item onSelect={onSelect} className="min-h-9 gap-6 py-1.5 text-sm">
      <span className="flex-1">{children}</span>
      {on && <CheckIcon className={`${GLYPH} text-ink`} />}
    </Dropdown.Item>
  );
}

/**
 * The models of one kind, searchable, each with its note under it — what the
 * desktop chip's popover and the phone sheet's "Select a model" view both draw.
 *
 * Labelled by the registry key, which is what the skills and the CLI call
 * it; the Replicate id is what goes out. No cost beside a name — the
 * registry carries no price and a number invented from a typical run would
 * be a claim this app cannot back.
 */
export function ModelList({
  kind,
  models,
  entry,
  onModel,
  autoFocus = false,
}: {
  kind: RunKind;
  models: Record<string, ModelEntry>;
  entry: ModelEntry;
  /** The Replicate `owner/name` of the chosen model. */
  onModel: (model: string) => void;
  autoFocus?: boolean;
}) {
  const [query, setQuery] = useState("");

  const offered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return Object.values(models)
      .filter((each) => each.kind === kind)
      .filter(
        (each) =>
          q === "" ||
          each.key.toLowerCase().includes(q) ||
          each.model.toLowerCase().includes(q) ||
          (each.note ?? "").toLowerCase().includes(q),
      )
      .sort((a, b) => a.key.localeCompare(b.key));
  }, [kind, models, query]);

  return (
    <div className="flex flex-col gap-2">
      <Input
        aria-label="Search models"
        placeholder="Search models…"
        value={query}
        onValueChange={setQuery}
        autoFocus={autoFocus}
      />
      <ul className="flex flex-col" role="listbox" aria-label="Models">
        {offered.map((each) => {
          const on = each.model === entry.model;
          return (
            <li key={each.model} role="presentation">
              <Button
                intent="secondary"
                size="sm"
                wrap
                role="option"
                aria-selected={on}
                className={`h-auto w-full justify-start gap-3 rounded-sm px-2 py-2 text-left
                            hover:bg-fill active:bg-fill-active
                            ${on ? "bg-fill" : "bg-transparent"}`}
                onClick={() => onModel(each.model)}
              >
                <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-sm bg-fill-hover text-ink">
                  <ModelIcon className={GLYPH} />
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="flex items-center gap-2">
                    <Text as="span" variant="body" weight="medium" className="truncate">
                      {each.key}
                    </Text>
                    {on && <CheckIcon className={`${GLYPH} text-ink`} />}
                  </span>
                  {each.note && (
                    <Text variant="caption" tone="muted" className="line-clamp-2 whitespace-normal">
                      {each.note}
                    </Text>
                  )}
                </span>
              </Button>
            </li>
          );
        })}
        {offered.length === 0 && (
          <li className="px-2 py-3">
            <EmptyState title={`Nothing here matches “${query}”.`} />
          </li>
        )}
      </ul>
    </div>
  );
}

/** The model chip, and the list behind it — hung upward from the chip row. */
export function ModelChip({
  kind,
  models,
  entry,
  onModel,
}: {
  kind: RunKind;
  models: Record<string, ModelEntry>;
  entry: ModelEntry;
  onModel: (model: string) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger
        aria-label={`Model: ${entry.key}`}
        title="Model"
        className={`${chipClass} text-ink max-md:bg-fill`}
      >
        <ModelIcon className={GLYPH} />
        <span className="max-w-40 truncate">{entry.key}</span>
        <ChevronDownIcon className="size-3.5 shrink-0 fill-none stroke-current stroke-[1.5] text-muted" />
      </Popover.Trigger>
      <Popover.Content
        label="Models"
        className={`${MENU_UP} max-h-[70vh] w-[min(24rem,calc(100vw-2rem))] max-w-none overflow-y-auto p-2`}
      >
        <ModelList
          kind={kind}
          models={models}
          entry={entry}
          autoFocus
          onModel={(model) => {
            onModel(model);
            setOpen(false);
          }}
        />
      </Popover.Content>
    </Popover.Root>
  );
}

/**
 * One setting as a row: the word on the left, the control on the right —
 * the shape ElevenLabs' sheet gives every setting, and the shape both the
 * phone sheet and the desktop `More options` panel draw here. A form with a
 * label, a mono key, a full-width select and a paragraph under each was the
 * old `SchemaParams` shape, and it is not this.
 */
export function SettingRow({
  label,
  hint,
  children,
}: {
  label: string;
  /** The schema's description, a hover away rather than a paragraph. */
  hint?: string | undefined;
  children: React.ReactNode;
}) {
  return (
    <div
      className="flex min-h-12 items-center justify-between gap-3 border-b border-line last:border-b-0"
      data-setting-row=""
    >
      <Text as="span" variant="body" title={hint}>
        {label}
      </Text>
      <span className="flex shrink-0 items-center rounded-sm bg-fill">{children}</span>
    </div>
  );
}

/**
 * The chip row's six, as rows. Each is the same `ParamChip` the desktop row
 * draws, so a value set on either is the same value.
 */
export function ParamRows({
  entry,
  params,
  onParams,
}: {
  entry: ModelEntry;
  params: Record<string, unknown>;
  onParams: (next: Record<string, unknown>) => void;
}) {
  const schema = useLiveSchema(entry.model);
  const chips = useMemo(() => resolveChips(entry, schema), [entry, schema]);
  if (chips.length === 0) return null;

  return (
    <div className="flex flex-col" data-param-rows="">
      {chips.map((chip) => (
        <SettingRow key={chip.name} label={chip.spec.label}>
          <ParamChip
            chip={chip}
            value={params[chip.name]}
            menuSide="down"
            onChange={(next) => onParams(withParam(params, chip.name, next))}
          />
        </SettingRow>
      ))}
    </div>
  );
}

/** `params` with one value set, or with it unset when `next` is undefined. */
function withParam(
  params: Record<string, unknown>,
  name: string,
  next: unknown,
): Record<string, unknown> {
  const out = { ...params };
  if (next === undefined) delete out[name];
  else out[name] = next;
  return out;
}

/**
 * Everything the model takes that has no chip, as rows — `More options`.
 *
 * Read off the LIVE schema through `describedProps`, which already drops the
 * prompt, the image fields (sends, never params — hard rule #3), and any
 * credential-shaped name; `skip` adds the six chips so nothing is offered
 * twice. What each row's control is follows the input's shape: a listed or
 * short-ranged value is a menu, a yes/no is a switch, and anything else is a
 * small box. The model's own default is what an empty control shows, and an
 * untouched row writes nothing — see `ParamChip`.
 */
export function SettingRows({
  schema,
  skip,
  params,
  onParams,
}: {
  schema: ModelSchema;
  skip: ReadonlySet<string>;
  params: Record<string, unknown>;
  onParams: (next: Record<string, unknown>) => void;
}) {
  const rows = describedProps(schema, skip);
  if (rows.length === 0) return null;
  const schemas = schema.schemas ?? {};

  return (
    <div className="flex flex-col" data-setting-rows="">
      {rows.map(({ name, spec, kind }) => {
        const label = humaniseKey(name);
        const hint = typeof spec.description === "string" ? spec.description : undefined;
        const value = params[name];
        const set = (next: unknown) => onParams(withParam(params, name, next));
        const choices =
          kind === "enum"
            ? (enumOf(spec, schemas) ?? [])
            : kind === "number"
              ? rangeChoices(spec)
              : [];

        if (kind === "boolean") {
          return (
            <SettingRow key={name} label={label} hint={hint}>
              <SwitchChip
                label={label}
                on={(value ?? spec.default) === true}
                onChange={set}
              />
            </SettingRow>
          );
        }
        if (choices.length > 0) {
          return (
            <SettingRow key={name} label={label} hint={hint}>
              <ValueChip
                label={label}
                value={value}
                modelDefault={spec.default}
                choices={choices}
                onChange={set}
              />
            </SettingRow>
          );
        }
        return (
          <SettingRow key={name} label={label} hint={hint}>
            <Input
              aria-label={label}
              type={kind === "number" ? "number" : "text"}
              value={value === undefined || value === null ? "" : String(value)}
              placeholder={
                spec.default === undefined || spec.default === null
                  ? "Default"
                  : `Default · ${String(spec.default)}`
              }
              className="h-8 w-36 border-0 bg-transparent px-2 text-right text-sm"
              onValueChange={(text: string) =>
                set(
                  text === ""
                    ? undefined
                    : kind === "number" && text.trim() !== "" && !Number.isNaN(Number(text))
                      ? Number(text)
                      : text,
                )
              }
            />
          </SettingRow>
        );
      })}
    </div>
  );
}

/** A yes/no as the same chip the audio chip is: a word that flips. */
function SwitchChip({
  label,
  on,
  onChange,
}: {
  label: string;
  on: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <Button
      intent="secondary"
      size="sm"
      role="switch"
      aria-checked={on}
      aria-label={label}
      className={chipClass}
      onClick={() => onChange(!on)}
    >
      {on ? "On" : "Off"}
    </Button>
  );
}

/** A listed value as a chip with no glyph: the value, a chevron, a menu. */
function ValueChip({
  label,
  value,
  modelDefault,
  choices,
  onChange,
}: {
  label: string;
  value: unknown;
  modelDefault: unknown;
  choices: unknown[];
  onChange: (next: unknown) => void;
}) {
  const shown = value === undefined ? modelDefault : value;
  const text = shown === undefined || shown === null ? "Auto" : String(shown);
  return (
    <Dropdown.Root>
      <Dropdown.Trigger aria-label={`${label}: ${text}`} className={chipClass}>
        {text}
        <ChevronDownIcon className="size-3.5 shrink-0 fill-none stroke-current stroke-[1.5] text-muted" />
      </Dropdown.Trigger>
      <Dropdown.Content className="right-0 left-auto max-h-80 overflow-y-auto">
        <Dropdown.Label>{label}</Dropdown.Label>
        <MenuItem on={value === undefined} onSelect={() => onChange(undefined)}>
          Default
          {modelDefault !== undefined && modelDefault !== null && (
            <span className="ml-1 text-muted">· {String(modelDefault)}</span>
          )}
        </MenuItem>
        {choices.map((choice) => (
          <MenuItem
            key={String(choice)}
            on={value !== undefined && String(value) === String(choice)}
            onSelect={() => onChange(choice)}
          >
            {String(choice)}
          </MenuItem>
        ))}
      </Dropdown.Content>
    </Dropdown.Root>
  );
}
