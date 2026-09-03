import { useCallback, useEffect, useState } from "react";

import { Alert, Badge, Button, Text, Textarea } from "@ansavva/design-system";

import { SectionLoading } from "../common/SectionLoading";
import { getNodeText, saveNodeText } from "../../apis/studio";
import { copyLabel, useCopyToClipboard } from "../../hooks/useCopyToClipboard";
import { formatTextContent } from "../../utils/format";
import type { FileEntry, TextResponse } from "../../types";
import { CopyKeyButton } from "../common/CopyKeyButton";
import { PageBar, type Crumb } from "../layout/PageBar";
import { MarkdownView } from "./MarkdownView";

interface Props {
  file: FileEntry;
  onClose: () => void;
  /** Called after a successful save, so the listing behind this can re-fetch. */
  onSaved?: () => void;
  /** Where the page sits — the folder this file is in, as one crumb. */
  crumbs?: Crumb[];
}

/**
 * A whole page for one text file — the pipeline's `request.json`, `result.json`,
 * `prompt.json` and `scene.json`, the subject `profile.yaml` files,
 * `phrasebook/wording.yaml` and the reference captions.
 *
 * **It is `AppLayout` with a `PageBar` now, not a `fixed inset-0` takeover.**
 * It used to fill the viewport and lock the body's own scroll the way the old
 * media viewer did, because there was no page to put it on. `ObjectPage`
 * became an ordinary page for the same reason (`ObjectHeader`'s own note), and
 * this follows: a `profile.yaml` is a thing you sit and read, and reading it
 * behind its own header — with the same crumb back to the folder every other
 * screen draws — is the app's one shape rather than a second one for text.
 *
 * Two decisions inside the editor are worth knowing:
 *
 * * **The editor holds the file's bytes, not the pretty-printed view.** JSON is
 *   reformatted for *reading* by `formatTextContent`, and saving that back would
 *   rewrite the whitespace of a file the pipeline wrote, in a diff nobody asked
 *   for. So pressing Edit shows exactly what is in the bucket.
 * * **A truncated file cannot be edited at all.** `/api/text` caps what it
 *   returns, so a file over the cap arrives with its tail missing, and saving
 *   that would delete the rest. The backend refuses an oversized body too, but
 *   this is the half that stops it from ever being attempted.
 *
 * Nothing here interprets the contents. The pipeline owns their shape
 * and changes it freely, so the viewer shows what is in the file — pretty-printed
 * for JSON, rendered for markdown, raw otherwise — and never claims to know what
 * a field means. That is unchanged by making it writable: you are editing text,
 * not filling in a form the pipeline would have to keep honouring.
 */
export function TextPage({ file, onClose, onSaved, crumbs }: Props) {
  const [data, setData] = useState<TextResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [raw, setRaw] = useState(false);

  const [draft, setDraft] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  const contentCopy = useCopyToClipboard();

  const editing = draft !== null;
  const dirty = editing && draft !== data?.content;

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    setDraft(null);

    getNodeText(file.id)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });

    return () => {
      cancelled = true;
    };
  }, [file.id]);

  /**
   * Leaving with unsaved edits asks once.
   *
   * Not a `confirm()` and not a dialog — the page turns its own header into the
   * question, which is the same reasoning `ConfirmDeleteButton` sets out: a
   * prompt that appears where your attention already is cannot be dismissed
   * without being read.
   */
  const close = useCallback(() => {
    if (dirty && !confirmDiscard) {
      setConfirmDiscard(true);
      return;
    }
    onClose();
  }, [confirmDiscard, dirty, onClose]);

  // Escape closes only while nothing is dirty — a dirty Escape arms the same
  // "leave without saving" question the header offers, rather than leaving.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [close]);

  // A reload or a closed tab is the one exit this component cannot intercept, so
  // it is handed to the browser's own prompt.
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  const save = useCallback(() => {
    if (draft === null) return;
    setSaving(true);
    setSaveError(null);

    // By node id in both directions now. The read and the write used to address
    // the same file through two different resolvers — an id here, a name path
    // there — which is the last of what #432 left open.
    saveNodeText(file.id, draft)
      .then(() => {
        // The saved draft becomes the file: staying in the editor is what you
        // want after a save, and re-fetching to prove it would only be a chance
        // to overwrite what is on screen with a stale read.
        setData((current) => (current ? { ...current, content: draft } : current));
        setDraft(null);
        setConfirmDiscard(false);
        onSaved?.();
      })
      .catch((err: Error) => setSaveError(err.message))
      .finally(() => setSaving(false));
  }, [draft, file.id, onSaved]);

  const isMarkdown = data?.language === "markdown";
  const editable = data !== null && !data.truncated;

  return (
    <>
      <PageBar
        crumbs={crumbs}
        actions={
          <>
            {data && (
              <Badge intent="neutral" className="font-mono">
                {data.language}
              </Badge>
            )}

            {/* Rendered/raw is a *reading* choice, so it is gone while editing —
                there is only one way to edit markdown and it is as markdown. */}
            {isMarkdown && !editing && (
              <Button intent="secondary" size="sm" onClick={() => setRaw((value) => !value)}>
                {raw ? "Rendered" : "Raw"}
              </Button>
            )}

            {/* Two different things are copyable here and the labels say which: the
                file's contents, and the key that names the file. */}
            <CopyKeyButton value={file.key} />
            {data && !editing && (
              <Button
                intent="secondary"
                size="sm"
                onClick={() => void contentCopy.copy(data.content)}
              >
                {copyLabel(contentCopy.status, "Copy text")}
              </Button>
            )}

            {editing ? (
              <>
                <Button size="sm" disabled={saving || !dirty} onClick={save}>
                  {saving ? "Saving…" : dirty ? "Save" : "Saved"}
                </Button>
                <Button
                  intent="secondary"
                  size="sm"
                  disabled={saving}
                  onClick={() => {
                    setDraft(null);
                    setSaveError(null);
                    setConfirmDiscard(false);
                  }}
                >
                  Cancel
                </Button>
              </>
            ) : (
              editable && (
                <Button size="sm" onClick={() => setDraft(data.content)}>
                  Edit
                </Button>
              )
            )}

            {confirmDiscard ? (
              <Button size="sm" onClick={onClose}>
                Leave without saving
              </Button>
            ) : (
              <Button intent="secondary" size="sm" onClick={close} aria-label="Close (Esc)">
                Close
              </Button>
            )}
          </>
        }
      >
        <Text variant="display" className="min-w-0 truncate">
          {file.name}
        </Text>
        {/* The name path — the thing `CopyKeyButton` beside it copies, and
            the thing a `studio` command is handed. */}
        <Text variant="caption" tone="muted" className="min-w-0 truncate font-mono">
          {file.key}
        </Text>
      </PageBar>

      {confirmDiscard && (
        <Text variant="caption" tone="muted">
          You have unsaved changes. Save to keep them, or leave without saving.
        </Text>
      )}

      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
        {error && (
          <Alert.Root intent="danger">
            <Alert.Title>Could not open this file</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        )}

        {saveError && (
          <Alert.Root intent="danger">
            <Alert.Title>Could not save this file</Alert.Title>
            <Alert.Description>{saveError}</Alert.Description>
          </Alert.Root>
        )}

        {!data && !error && <SectionLoading label="Loading file" />}

        {data && data.truncated && (
          <Alert.Root intent="warning">
            <Alert.Title>This file is too big to show in full</Alert.Title>
            <Alert.Description>
              Only the first part is here, so it cannot be edited — saving would drop the rest.
            </Alert.Description>
          </Alert.Root>
        )}

        {editing ? (
          <Textarea
            value={draft}
            onValueChange={setDraft}
            spellCheck={false}
            aria-label={`Contents of ${file.name}`}
            className="min-h-[60vh] rounded-none font-mono text-xs leading-relaxed"
          />
        ) : (
          data &&
          (isMarkdown && !raw ? (
            <MarkdownView source={data.content} />
          ) : (
            <pre className="overflow-x-auto font-mono text-xs leading-relaxed text-ink">
              <code>{formatTextContent(data.content, data.language)}</code>
            </pre>
          ))
        )}
      </div>
    </>
  );
}
