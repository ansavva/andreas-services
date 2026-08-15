import { useEffect, useState } from "react";

import { Alert, Badge, Spinner, Text } from "@ansavva/design-system";

import { getText } from "../../apis/studio";
import { copyLabel, useCopyToClipboard } from "../../hooks/useCopyToClipboard";
import { formatTextContent } from "../../utils/format";
import type { FileEntry, TextResponse } from "../../types";
import { CopyKeyButton } from "../common/CopyKeyButton";
import { MarkdownView } from "./MarkdownView";

interface Props {
  file: FileEntry;
  onClose: () => void;
}

/**
 * Read-only viewer for the pipeline's `request.json`, `result.json`,
 * `prompt.json`, the subject `profile.md` files and the reference captions.
 *
 * Nothing here interprets the contents. The x-harness pipeline owns their shape
 * and changes it freely, so the viewer shows what is in the file — pretty-printed
 * for JSON, rendered for markdown, raw otherwise — and never claims to know what
 * a field means.
 */
export function CodeViewer({ file, onClose }: Props) {
  const [data, setData] = useState<TextResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [raw, setRaw] = useState(false);
  const contentCopy = useCopyToClipboard();

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);

    getText(file.key)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });

    return () => {
      cancelled = true;
    };
  }, [file.key]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);

    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  const isMarkdown = data?.language === "markdown";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={file.name}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-0 sm:p-6"
      onClick={onClose}
    >
      <div
        onClick={(event) => event.stopPropagation()}
        className="flex h-full w-full max-w-4xl flex-col overflow-hidden border border-line bg-card
                   sm:h-[85vh] sm:rounded-lg"
      >
        <header className="flex items-center gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0 flex-1">
            <Text variant="title" className="truncate">
              {file.name}
            </Text>
            <Text variant="caption" tone="muted" className="truncate">
              {file.key}
            </Text>
          </div>

          {data && <Badge intent="neutral">{data.language}</Badge>}

          {isMarkdown && (
            <HeaderButton onClick={() => setRaw((value) => !value)}>
              {raw ? "Rendered" : "Raw"}
            </HeaderButton>
          )}
          {/* Two different things are copyable here and the labels say which:
              the file's contents, and the key that names the file. */}
          <CopyKeyButton value={file.key} />
          {data && (
            <HeaderButton onClick={() => void contentCopy.copy(data.content)}>
              {copyLabel(contentCopy.status, "Copy text")}
            </HeaderButton>
          )}
          <HeaderButton onClick={onClose} aria-label="Close (Esc)">
            Close
          </HeaderButton>
        </header>

        <div className="min-h-0 flex-1 overflow-auto">
          {error && (
            <div className="p-4">
              <Alert.Root intent="danger">
                <Alert.Title>Could not open this file</Alert.Title>
                <Alert.Description>{error}</Alert.Description>
              </Alert.Root>
            </div>
          )}

          {!data && !error && (
            <div className="flex h-full items-center justify-center">
              <Spinner size="md" label="Loading file" />
            </div>
          )}

          {data && (isMarkdown && !raw ? (
            <MarkdownView source={data.content} />
          ) : (
            <pre
              className="overflow-x-auto p-4 font-mono text-xs leading-relaxed text-ink"
              // `readOnly` has no meaning on a <pre>; this is display-only by
              // construction — there is no editor and no write path in the API.
            >
              <code>{formatTextContent(data.content, data.language)}</code>
            </pre>
          ))}

          {data?.truncated && (
            <div className="border-t border-line px-4 py-3">
              <Text variant="caption" tone="muted">
                This file was truncated for display.
              </Text>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function HeaderButton({
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className="shrink-0 rounded-md border border-line px-2.5 py-1.5 font-body text-xs text-ink
                 transition-colors hover:bg-surface-alt
                 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
    >
      {children}
    </button>
  );
}
