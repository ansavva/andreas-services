import type { ReactNode } from "react";

import { Text } from "@ansavva/design-system";

/**
 * A plan's parameters as chips, and the model beside them.
 *
 * **Scalars only.** A structured parameter — a list of reference weights, a
 * nested block — is not a `key value` pill; it is the plan document's, and
 * the opened run's Request row is where it reads whole. The feed and the
 * rail draw the same chips from this one place, so a parameter reads the
 * same in both.
 *
 * **A long value wraps inside its pill; the pill never leaves its column.**
 * These were `whitespace-nowrap`, which was right for `seed 990001` and wrong
 * the first time a model with a real `negative_prompt` landed in the feed: a
 * sentence-long value ran the pill out past the row's edge and under the
 * thumbnail beside it. The key stays on one line; the value may take several.
 */
export function ParamChips({
  params,
  model,
  leading,
  trailing,
}: {
  params: Record<string, unknown> | undefined;
  model?: string;
  /** Tags drawn before the parameters — the run's cast, as `CharacterTag`s. */
  leading?: ReactNode;
  /** Tags drawn after the model — the cost and the seconds, on the rail. */
  trailing?: ReactNode;
}) {
  const entries = scalarParams(params);
  if (entries.length === 0 && !model && !leading && !trailing) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {leading}
      {entries.map(([key, value]) => (
        <span
          key={key}
          // `sm`, the create bar's chip corner (`CreateChips`): a fact on a
          // run and a choice on the bar are the same small thing. A status
          // `Badge` stays a pill; a shape, not a corner.
          className="inline-flex max-w-full items-baseline gap-1.5 rounded-sm border border-line bg-card px-2 py-0.5"
        >
          {/* `inline` on BOTH: this pair is a `key value` pill sharing one
              line — the minority case `Text`'s `inline` prop exists for. */}
          <Text variant="caption" tone="muted" inline className="whitespace-nowrap">
            {key}
          </Text>
          <Text variant="caption" inline className="min-w-0 break-words">
            {value}
          </Text>
        </span>
      ))}
      {model && (
        <span className="inline-flex items-baseline whitespace-nowrap rounded-sm border border-line bg-card px-2 py-0.5">
          <Text variant="caption" family="mono" inline>
            {model}
          </Text>
        </span>
      )}
      {trailing}
    </div>
  );
}

/** The parameters a chip or a grid row draws: scalars, and not the prose ones. */
export function scalarParams(params: Record<string, unknown> | undefined): Array<[string, string]> {
  return Object.entries(params ?? {})
    .filter(([key, value]) => isScalar(value) && !PROSE.has(key))
    .map(([key, value]) => [key, String(value)]);
}

/**
 * Parameters that are prose rather than a setting — drawn under the prompt
 * by `RunPrompt`, in the prompt's own shape, and not as a pill here.
 */
const PROSE = new Set(["negative_prompt"]);

function isScalar(value: unknown): boolean {
  return (
    typeof value === "string" || typeof value === "number" || typeof value === "boolean"
  );
}
