import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Alert, Button, Card, Field, Input, Spinner, Text } from "@ansavva/design-system";

import {
  completeUpload,
  createPage,
  getPage,
  listFiles,
  putToS3,
  signUploads,
  updatePage,
} from "../api";
import { collectLessonFiles, LessonFilesError, type LessonFile } from "../lessonFiles";

/**
 * Name a lesson and upload the files that make it.
 *
 * **There is no editor here, deliberately.** She authors the lesson in whatever
 * tool she already uses and this publishes what that tool produced, untouched —
 * her styling, her layout and her interactive scripts all survive, because
 * nothing rewrites or sanitizes them. What makes that safe is that lessons are
 * served from a different origin to this app; see `infra/modules/lesson_hosting`.
 *
 * Three ways in, one code path: `collectLessonFiles` turns a single `.html`, a
 * `.zip`, or a chosen folder into the same list of (path, blob) before anything
 * is signed.
 */
export function PageEditorPage() {
  const { pageId } = useParams<{ pageId: string }>();
  const navigate = useNavigate();
  const isNew = pageId === undefined;

  const [title, setTitle] = useState("");
  const [files, setFiles] = useState<string[]>([]);
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);

  const filePicker = useRef<HTMLInputElement>(null);
  const folderPicker = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isNew || !pageId) return;
    Promise.all([getPage(pageId), listFiles(pageId)])
      .then(([page, uploaded]) => {
        setTitle(page.title);
        setFiles(uploaded);
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Could not load that page."),
      )
      .finally(() => setLoading(false));
  }, [isNew, pageId]);

  const saveTitle = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      if (isNew) {
        const page = await createPage({ title });
        navigate(`/pages/${page.id}`, { replace: true });
      } else if (pageId) {
        await updatePage(pageId, { title });
        navigate("/");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not save that page.");
    } finally {
      setSaving(false);
    }
  }, [isNew, pageId, title, navigate]);

  /**
   * Sign, PUT, then confirm.
   *
   * Uploads run a few at a time rather than all at once: a lesson can be two
   * hundred files, and firing that many parallel PUTs at a school connection
   * makes every one of them slower and some of them fail.
   */
  const upload = useCallback(
    async (chosen: File[]) => {
      if (!pageId) return;
      setError(null);
      let lessonFiles: LessonFile[];
      try {
        lessonFiles = await collectLessonFiles(chosen);
      } catch (err: unknown) {
        setError(
          err instanceof LessonFilesError
            ? err.message
            : "Could not read those files.",
        );
        return;
      }

      setProgress({ done: 0, total: lessonFiles.length });
      try {
        const signed = await signUploads(
          pageId,
          lessonFiles.map((f) => f.path),
        );
        const byPath = new Map(lessonFiles.map((f) => [f.path, f.blob]));

        let done = 0;
        const queue = [...signed];
        const worker = async () => {
          for (let next = queue.shift(); next; next = queue.shift()) {
            const blob = byPath.get(next.path);
            if (blob) await putToS3(next, blob);
            done += 1;
            setProgress({ done, total: signed.length });
          }
        };
        await Promise.all([worker(), worker(), worker(), worker()]);

        const page = await completeUpload(pageId);
        setFiles(page.files);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "The upload did not finish.");
      } finally {
        setProgress(null);
      }
    },
    [pageId],
  );

  if (loading) {
    return (
      <div className="flex justify-center p-12">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <Text variant="display" family="heading">
        {isNew ? "New lesson" : "Lesson"}
      </Text>

      {error && (
        <div className="my-4">
          <Alert.Root intent="danger">
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        </div>
      )}

      <div className="mt-6 flex flex-col gap-6">
        <Field.Root name="title">
          <Field.Label>Name</Field.Label>
          <Input
            value={title}
            onValueChange={setTitle}
            placeholder="Warm Up: Solving for x"
          />
          <Field.Description>
            Just for your own list — students never see it.
          </Field.Description>
        </Field.Root>

        {isNew ? (
          <Alert.Root intent="info">
            <Alert.Description>
              Give the lesson a name and save it. You can upload its files on the
              next screen.
            </Alert.Description>
          </Alert.Root>
        ) : (
          <Card.Root>
            <Card.Title>Lesson files</Card.Title>
            <Text tone="muted">
              Upload the lesson exactly as your program saved it — one HTML file,
              a zip, or the whole folder. It needs to contain{" "}
              <strong>index.html</strong>, which is the page students open.
              Uploading again replaces everything.
            </Text>

            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                className="rounded-pill"
                disabled={progress !== null}
                onClick={() => filePicker.current?.click()}
              >
                Choose files
              </Button>
              <Button
                intent="secondary"
                className="rounded-pill"
                disabled={progress !== null}
                onClick={() => folderPicker.current?.click()}
              >
                Choose a folder
              </Button>
            </div>

            {/* Two inputs because `webkitdirectory` is a property of the input,
                not of the click — one picker cannot offer both. Hidden, and
                driven by the buttons above, so the styling is the design
                system's rather than the browser's. */}
            <input
              ref={filePicker}
              type="file"
              multiple
              accept=".html,.htm,.zip,image/*,text/css,text/javascript,font/*"
              className="hidden"
              onChange={(event) => {
                void upload([...(event.target.files ?? [])]);
                event.target.value = "";
              }}
            />
            <input
              ref={folderPicker}
              type="file"
              // Non-standard but supported everywhere this app runs; it is the
              // only way a browser will hand over a directory tree.
              {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
              multiple
              className="hidden"
              onChange={(event) => {
                void upload([...(event.target.files ?? [])]);
                event.target.value = "";
              }}
            />

            {progress && (
              <div className="mt-4 flex items-center gap-3">
                <Spinner />
                <Text variant="caption" tone="muted">
                  Uploading {progress.done} of {progress.total}…
                </Text>
              </div>
            )}

            {!progress && files.length > 0 && (
              <div className="mt-4">
                <Text variant="caption" tone="muted">
                  {files.length} file{files.length === 1 ? "" : "s"} uploaded
                </Text>
                <ul className="border-line mt-2 max-h-56 overflow-auto rounded-lg border">
                  {files.map((path) => (
                    <li
                      key={path}
                      className="border-line text-ink border-b px-3 py-1.5 font-mono text-xs last:border-b-0"
                    >
                      {path}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {!progress && files.length === 0 && (
              <div className="mt-4">
                <Text variant="caption" tone="muted">
                  Nothing uploaded yet.
                </Text>
              </div>
            )}
          </Card.Root>
        )}

        <div className="flex flex-wrap gap-2">
          <Button
            className="rounded-pill"
            onClick={() => void saveTitle()}
            disabled={saving || !title.trim()}
          >
            {saving ? "Saving…" : isNew ? "Create lesson" : "Save"}
          </Button>
          <Button
            intent="secondary"
            className="rounded-pill"
            onClick={() => navigate("/")}
            disabled={saving}
          >
            {isNew ? "Cancel" : "Done"}
          </Button>
        </div>
      </div>
    </div>
  );
}
