import { useState } from "react";

import { Badge, Button, Text } from "@ansavva/design-system";

import type { FileEntry } from "../../types";
import { downloadNode } from "../../utils/download";
import { formatBytes } from "../../utils/format";
import { describeBinary, extensionOf } from "../../utils/media";
import { CopyKeyButton } from "../common/CopyKeyButton";
import { PageBar, type Crumb } from "../layout/PageBar";

interface Props {
  file: FileEntry;
  onClose: () => void;
  crumbs?: Crumb[];
}

/**
 * A file the viewer cannot draw: weights, an archive, anything that is neither
 * a picture, a clip nor text.
 *
 * **A page, not a spinner.** `/o/<id>` is the address of every node, and the
 * first `.safetensors` opened at it was handed to the text page, which asked
 * the text route, was refused, and spun. What a person wants from a file like
 * this is to know what it is, how big it is, where it sits, and to get it —
 * so that is the whole page. The same bar the text page draws, so the two
 * kinds of non-media file open alike.
 */
export function FilePage({ file, onClose, crumbs }: Props) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const what = describeBinary(file.name);
  const ext = extensionOf(file.name).replace(/^\./, "") || "file";

  const download = async () => {
    setDownloading(true);
    setError(null);
    try {
      await downloadNode(file.id);
    } catch (err) {
      setError((err as Error).message || "Could not fetch this file.");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <>
      <PageBar
        crumbs={crumbs}
        title={file.name}
        meta={
          <Text variant="caption" tone="muted" className="min-w-0 truncate font-mono">
            {file.key}
          </Text>
        }
        actions={
          <>
            <Badge intent="neutral" className="font-mono">
              {ext}
            </Badge>
            <CopyKeyButton value={file.key} />
            <Button size="sm" disabled={downloading} onClick={() => void download()}>
              {downloading ? "Fetching…" : "Download"}
            </Button>
            <Button intent="secondary" size="sm" onClick={onClose} aria-label="Close (Esc)">
              Close
            </Button>
          </>
        }
      />

      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4" data-file-page="">
        <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 border border-line bg-card p-4">
          <dt>
            <Text variant="caption" tone="muted">
              Kind
            </Text>
          </dt>
          <dd>
            <Text variant="body">{what}</Text>
          </dd>
          <dt>
            <Text variant="caption" tone="muted">
              Size
            </Text>
          </dt>
          <dd>
            <Text variant="body" family="mono">
              {formatBytes(file.size)}
            </Text>
          </dd>
          <dt>
            <Text variant="caption" tone="muted">
              Type
            </Text>
          </dt>
          <dd>
            <Text variant="body" family="mono">
              {file.content_type || "unknown"}
            </Text>
          </dd>
        </dl>
        {what === "LoRA / model weights" && (
          <Text variant="caption" tone="muted">
            Weights a model loads beside its own. Nothing here draws them; a video run binds
            them with <span className="font-mono">--lora-high-key</span> /{" "}
            <span className="font-mono">--lora-low-key</span>.
          </Text>
        )}
        {error && (
          <Text variant="caption" className="text-danger">
            {error}
          </Text>
        )}
      </div>
    </>
  );
}
