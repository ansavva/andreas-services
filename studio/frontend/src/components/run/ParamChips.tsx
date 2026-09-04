import { Text } from "@ansavva/design-system";

/**
 * A plan's parameters as chips, and the model beside them.
 *
 * **Scalars only, and nothing wraps inside a chip.** A structured parameter —
 * a list of reference weights, a nested block — is not a `key value` pill;
 * it is the plan document's, and the opened run's Request row is where it
 * reads whole. The feed and the rail draw the same chips from this one
 * place, so a parameter reads the same in both.
 */
export function ParamChips({
  params,
  model,
}: {
  params: Record<string, unknown> | undefined;
  model?: string;
}) {
  const entries = Object.entries(params ?? {}).filter(([, value]) => isScalar(value));
  if (entries.length === 0 && !model) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([key, value]) => (
        <span
          key={key}
          className="inline-flex items-baseline gap-1.5 whitespace-nowrap rounded-none border border-line bg-card px-2 py-0.5"
        >
          {/* `inline` on BOTH: this pair is a `key value` pill sharing one
              line — the minority case `Text`'s `inline` prop exists for. */}
          <Text variant="caption" tone="muted" inline>
            {key}
          </Text>
          <Text variant="caption" inline>
            {String(value)}
          </Text>
        </span>
      ))}
      {model && (
        <span className="inline-flex items-baseline whitespace-nowrap rounded-none border border-line bg-card px-2 py-0.5">
          <Text variant="caption" family="mono" inline>
            {model}
          </Text>
        </span>
      )}
    </div>
  );
}

function isScalar(value: unknown): boolean {
  return (
    typeof value === "string" || typeof value === "number" || typeof value === "boolean"
  );
}
