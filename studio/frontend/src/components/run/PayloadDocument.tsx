import { useCallback, useState } from "react";

import { Text } from "@ansavva/design-system";

import { getNodeText, getRunPayloadPreview } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { formatTextContent } from "../../utils/format";
import { ChevronDownIcon } from "../common/icons";
import { LoadError } from "../common/LoadError";
import { SectionLoading } from "../common/SectionLoading";

/**
 * One payload document, as text.
 *
 * **Lifted out of the two-column run page when that page was deleted** — the
 * opened run's collapsed "Request" row is what draws these now, and the rule
 * they carry has not moved: `prompt.json`, `request.json` and `response.json`
 * are the provider's, studio stores them and decodes none of them, and this
 * shows them as text and nothing else.
 *
 * Fetched only when it is opened, because three of these on every opened run
 * is three requests for documents that are usually large and usually not what
 * the run was opened for.
 *
 * `formatTextContent` re-indents JSON **for reading** and is the only thing done
 * to it. That is not parsing in the sense the rule forbids: no field is looked
 * up, nothing branches on the shape, and what is shown is the same document.
 */
export function PayloadDocument({
  label,
  node,
  sent,
}: {
  label: string;
  node: string | null;
  /**
   * Whether this run has been submitted.
   *
   * An absent document means two different things and the page said one
   * sentence for both. On a draft nothing has gone out yet, so there is nothing
   * to record — and a person who has just edited the plan reasonably wonders
   * why `request.json` does not show the edit. On a submitted run an absent
   * document is a gap in the record instead.
   */
  sent: boolean;
}) {
  const load = useCallback(
    () =>
      node === null ? Promise.reject(new Error("absent")) : getNodeText(node),
    [node],
  );
  const [open, setOpen] = useState(false);
  const { data, loading, error, reload } = useResource(
    open && node !== null ? ["node-text", node] : null,
    load,
  );

  if (node === null) {
    return (
      <div className="border-t border-line py-2">
        <Text variant="caption" tone="muted" className="font-mono">
          {label} —{" "}
          {sent
            ? "not written for this run"
            : "written when this run is submitted"}
        </Text>
      </div>
    );
  }

  return (
    <div className="border-t border-line">
      {/* eslint-disable-next-line studio/no-hand-rolled-button -- a disclosure
          row, the same button-as-row shape as FileRow/FolderCard. */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 py-2 text-left transition-colors hover:text-muted
                   focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
      >
        <ChevronDownIcon
          className={`size-4 shrink-0 fill-none stroke-current stroke-[1.5] text-muted transition-transform
                      motion-reduce:transition-none ${open ? "" : "-rotate-90"}`}
        />
        {/* A file name, so mono — this is the one label on the page that is
            literally a path a person would type. */}
        <Text variant="body" family="mono">
          {label}
        </Text>
      </button>

      {open && (
        <div className="border-t border-line bg-card">
          {loading && <SectionLoading label={`Loading ${label}`} />}
          {error && (
            <div className="p-3">
              <LoadError what={label} message={error} onRetry={reload} />
            </div>
          )}
          {data && (
            // `whitespace-pre-wrap` + `break-words`, not `overflow-x-auto`.
            // A payload is mostly one very long line — a serialized prompt, or
            // a presigned URL with a signature on the end — so a scrolling
            // `<pre>` hid the half of it that mattered behind a gesture, and in
            // a narrow rail it hid most of it. `break-words` is what handles
            // the URLs, which carry no spaces to break at.
            <pre className="whitespace-pre-wrap break-words p-3 font-mono text-xs leading-relaxed text-ink">
              <code>{formatTextContent(data.content, data.language)}</code>
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * What a draft would send, fetched fresh.
 *
 * Re-read whenever the run record changes — an edit to the plan rewrites the
 * payload, and a preview that went stale the moment it was useful would be
 * worse than none. Built by the API from the same allowlist `submit` uses,
 * never re-derived here — see `getRunPayloadPreview`.
 */
export function PayloadPreview({ runId }: { runId: string }) {
  const load = useCallback(() => getRunPayloadPreview(runId), [runId]);
  const { data, loading, error } = useResource(["payload", runId], load);

  if (loading) return <SectionLoading label="Reading the request" />;
  if (error || !data) {
    return (
      <Text variant="caption" tone="muted">
        The request could not be built: {error ?? "nothing came back"}
      </Text>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <Text variant="caption" tone="muted" className="font-mono">
        request.json — what this run would send
      </Text>
      <pre className="max-h-96 overflow-y-auto whitespace-pre-wrap break-words rounded-none border border-line bg-card p-3 font-mono text-xs leading-relaxed text-ink">
        <code>{JSON.stringify(data.request, null, 2)}</code>
      </pre>
    </div>
  );
}
