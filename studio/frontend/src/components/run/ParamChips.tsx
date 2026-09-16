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
}: {
  params: Record<string, unknown> | undefined;
  model?: string;
}) {
  const entries = Object.entries(params ?? {}).filter(
    ([key, value]) => isScalar(value) && !PROSE.has(key),
  );
  if (entries.length === 0 && !model) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([key, value]) => (
        <span
          key={key}
          className="inline-flex max-w-full items-baseline gap-1.5 border border-line bg-card px-2 py-0.5"
        >
          {/* `inline` on BOTH: this pair is a `key value` pill sharing one
              line — the minority case `Text`'s `inline` prop exists for. */}
          <Text variant="caption" tone="muted" inline className="whitespace-nowrap">
            {key}
          </Text>
          <Text variant="caption" inline className="min-w-0 break-words">
            {String(value)}
          </Text>
        </span>
      ))}
      {model && (
        <span className="inline-flex items-baseline whitespace-nowrap border border-line bg-card px-2 py-0.5">
          <Text variant="caption" family="mono" inline>
            {model}
          </Text>
        </span>
      )}
    </div>
  );
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
