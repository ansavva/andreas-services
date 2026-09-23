import { useState } from "react";

import { Badge, IconButton, Text } from "@ansavva/design-system";

import type { FileEntry } from "../../types";
import { downloadNode } from "../../utils/download";
import { formatBytes } from "../../utils/format";
import { describeBinary, extensionOf, kindOfFile } from "../../utils/media";
import { CopyKeyButton } from "../common/CopyKeyButton";
import { CloseIcon, DownloadIcon } from "../common/icons";
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
 *
 * **The bar's controls are glyphs, the same ones the media viewer draws.**
 * They were labelled buttons — "Download", "Close" — and with the extension
 * badge beside them the row took a phone's width and the title truncated to
 * one letter. The badge is a fact about the file, so it sits in `meta` with
 * the path, as every other page's badges do.
 */
export function FilePage({ file, onClose, crumbs }: Props) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const what = describeBinary(file.name);
  const ext = extensionOf(file.name).replace(/^\./, "") || "file";
  /**
   * Audio is the one kind here that can be *played* rather than only
   * described, and it is on this page for the reason everything else is: the
   * viewer draws pictures and clips, and a voice sample is neither. The
   * browser's own controls are the whole player — a scrub bar, a volume, a
   * duration — and building a second one would add nothing a person asked for.
   */
  const isAudio = kindOfFile(file.name, file.content_type) === "audio";

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
          <>
            <Badge intent="neutral" className="font-mono">
              {ext}
            </Badge>
            <Text variant="caption" family="mono" tone="muted" className="min-w-0 truncate">
              {file.key}
            </Text>
          </>
        }
        actions={
          <>
            <CopyKeyButton value={file.key} />
            <IconButton
              label={downloading ? "Fetching…" : "Download"}
              size="sm"
              disabled={downloading}
              onClick={() => void download()}
            >
              <DownloadIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
            </IconButton>
            <IconButton label="Close (Esc)" size="sm" onClick={onClose}>
              <CloseIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
            </IconButton>
          </>
        }
      />

      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4" data-file-page="">
        {/* No caption track on a voice sample; the bar above names the file. */}
        {isAudio && (
          <audio
            src={file.url ?? undefined}
            controls
            preload="metadata"
            className="w-full"
            data-audio-player=""
          />
        )}
        <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 rounded-md border border-line bg-card p-4">
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
        {isAudio && (
          <Text variant="caption" tone="muted">
            A voice sample. Kling on fal binds one only to a video element, never to stills,
            and studio cannot bind a video element yet — so{" "}
            <span className="font-mono">--voice-key</span> and the Voice tile have nothing to
            bind it to today. Leave it off and Kling invents the voice. 5–30 seconds of one
            clean voice is what the model will ask for.
          </Text>
        )}
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
