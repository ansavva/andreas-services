import { Alert, Button, Progress, Text } from "@ansavva/design-system";

import type { UploadItem } from "../../hooks/useUploads";
import { formatBytes } from "../../utils/format";

interface Props {
  items: readonly UploadItem[];
  onClearFinished: () => void;
}

/**
 * What each queued file is doing, one row apiece.
 *
 * **A determinate bar, which is the only reason `apis/upload` uses
 * `XMLHttpRequest`.** `fetch` reports nothing about a request body on its way
 * out, so a `fetch` upload can only ever draw `Progress` with a `null` value —
 * the indeterminate pulse — and a pulse is indistinguishable from a hang for the
 * ten minutes a large clip takes over a phone connection. The bar is the feature.
 *
 * A finished row still says something worth reading: `landedAs` is the name the
 * catalog actually gave the file, which differs from the one picked whenever the
 * folder already held it (`clip.mp4` → `clip (2).mp4`). Uploading and then
 * hunting for a file under a name it does not have is the failure this line
 * exists to prevent.
 *
 * Rows are cleared by a press, never by a timer — see `useUploads.clearFinished`.
 */
export function UploadStatus({ items, onClearFinished }: Props) {
  if (items.length === 0) return null;

  const finished = items.filter((item) => item.status === "done").length;

  return (
    <section
      aria-label="Uploads"
      className="flex flex-col gap-2 rounded-none border border-line bg-card p-3"
    >
      {items.map((item) => (
        <div key={item.key} className="flex flex-col gap-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
            <Text variant="caption" className="min-w-0 truncate font-mono">
              {item.name}
            </Text>
            {/* Byte counts and a landed-as name: metadata either way. */}
            <Text variant="caption" tone="muted" className="font-mono tabular-nums">
              {describe(item)}
            </Text>
          </div>

          {/* Only while it is moving. A finished row is a sentence, and a full
              bar left under it reads as something still going. */}
          {item.status !== "done" && item.status !== "failed" && (
            <Progress.Root value={item.loaded} max={item.total || 1}>
              <Progress.Track>
                <Progress.Indicator />
              </Progress.Track>
            </Progress.Root>
          )}

          {/* `Alert` rather than a red `Text`: the package has no `danger` tone
              on `Text` on purpose, and this is the component it has for saying
              a thing went wrong. The title is the one every failure in the app
              wears, and says "this file" because the row above names it. */}
          {item.error && (
            <Alert.Root intent="danger">
              <Alert.Title>Could not upload this file</Alert.Title>
              <Alert.Description>{item.error}</Alert.Description>
            </Alert.Root>
          )}
        </div>
      ))}

      {finished > 0 && (
        <div className="flex justify-end">
          <Button intent="secondary" size="sm" onClick={onClearFinished}>
            Clear finished
          </Button>
        </div>
      )}
    </section>
  );
}

/** The right-hand caption for one row: size, progress, or what it landed as. */
function describe(item: UploadItem): string {
  if (item.status === "waiting") return `${formatBytes(item.total)} — waiting`;
  if (item.status === "failed") return "failed";
  if (item.status === "done") {
    return item.landedAs && item.landedAs !== item.name
      ? `uploaded as ${item.landedAs}`
      : "uploaded";
  }
  return `${formatBytes(item.loaded)} of ${formatBytes(item.total)}`;
}
