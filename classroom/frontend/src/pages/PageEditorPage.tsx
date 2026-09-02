import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Field,
  Input,
  Spinner,
  Text,
  Textarea,
} from "@ansavva/design-system";

import { createPage, getPage, updatePage } from "../api";

/**
 * Author or edit one page.
 *
 * The HTML box is deliberately a plain textarea rather than a rich editor. What
 * a teacher pastes here is most often already HTML — exported from a worksheet,
 * copied from another site — and a WYSIWYG layer would fight that paste rather
 * than accept it. The preview below is the feedback loop instead.
 *
 * The preview renders the *unsaved* draft, so it deliberately does NOT use
 * `dangerouslySetInnerHTML`: the draft has not been through the server's
 * sanitizer yet, and rendering it live would execute anything the teacher
 * pasted, in their own session. It is shown as escaped source until saved; the
 * reader at /p/<slug> is where sanitized output is rendered for real.
 */
export function PageEditorPage() {
  const { pageId } = useParams<{ pageId: string }>();
  const navigate = useNavigate();
  const isNew = pageId === undefined;

  const [title, setTitle] = useState("");
  const [html, setHtml] = useState("");
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isNew || !pageId) return;
    getPage(pageId)
      .then((page) => {
        setTitle(page.title);
        setHtml(page.html);
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Could not load that page."),
      )
      .finally(() => setLoading(false));
  }, [isNew, pageId]);

  const save = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      if (isNew) {
        const page = await createPage({ title, html });
        navigate(`/pages/${page.id}`, { replace: true });
      } else if (pageId) {
        await updatePage(pageId, { title, html });
        navigate("/");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not save that page.");
    } finally {
      setSaving(false);
    }
  }, [isNew, pageId, title, html, navigate]);

  if (loading) {
    return (
      <div className="flex justify-center p-12">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <Text variant="display" family="heading">
        {isNew ? "New page" : "Edit page"}
      </Text>

      {error && (
        <div className="my-4">
          <Alert.Root intent="danger">
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        </div>
      )}

      <div className="mt-6 flex flex-col gap-5">
        <Field.Root name="title">
          <Field.Label>Title</Field.Label>
          <Input
            value={title}
            onValueChange={setTitle}
            placeholder="Warm Up: Solving for x"
          />
          <Field.Description>
            Students see this at the top of the page.
          </Field.Description>
        </Field.Root>

        <Field.Root name="html">
          <Field.Label>Page content (HTML)</Field.Label>
          <Textarea
            value={html}
            onValueChange={setHtml}
            rows={16}
            placeholder="<h2>Today's warm up</h2><p>Solve for x…</p>"
          />
          <Field.Description>
            Headings, lists, tables, images and links are kept. Scripts, iframes
            and embedded forms are stripped when the page is saved.
          </Field.Description>
        </Field.Root>

        <div className="flex gap-2">
          <Button onClick={() => void save()} disabled={saving || !title.trim()}>
            {saving ? "Saving…" : "Save"}
          </Button>
          <Button intent="secondary" onClick={() => navigate("/")} disabled={saving}>
            Cancel
          </Button>
        </div>

        {html.trim() && (
          <div>
            <Text variant="title">Draft source</Text>
            <Text variant="caption" tone="muted">
              Shown as source, not rendered — an unsaved draft has not been
              sanitized yet. Save and open the share link to see the real page.
            </Text>
            <pre className="bg-surface-alt mt-2 max-h-80 overflow-auto rounded-lg p-3 text-xs">
              {html}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
