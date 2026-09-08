import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Alert,
  AlertDialog,
  Badge,
  Button,
  Card,
  Spinner,
  Text,
} from "@ansavva/design-system";

import { deletePage, listPages, updatePage } from "../api";
import type { PageSummary } from "../api";
import { PagesFilterBar, type PageFilter } from "../components/PagesFilterBar";

/** Everything the signed-in teacher has made, newest first. */
export function PagesListPage() {
  const navigate = useNavigate();
  const [pages, setPages] = useState<PageSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<PageFilter>("all");
  /** The page a confirmation is currently open for, if any. */
  const [pendingDelete, setPendingDelete] = useState<PageSummary | null>(null);

  const load = useCallback(() => {
    listPages()
      .then(setPages)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Could not load your pages."),
      );
  }, []);

  useEffect(load, [load]);

  async function togglePublished(page: PageSummary) {
    setBusyId(page.id);
    setError(null);
    try {
      await updatePage(page.id, { published: !page.published });
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not update that page.");
    } finally {
      setBusyId(null);
    }
  }

  /**
   * Delete, once the dialog below has been agreed to.
   *
   * **`window.confirm` used to guard this and it silently did not work.** A
   * browser is free to suppress a native dialog — Chrome does it for a page
   * that has produced several, and an automated one never shows it at all — and
   * a suppressed `confirm()` returns `false`, so this function simply returned
   * and no request was ever made. The button looked dead, with nothing in the
   * console and nothing on the network.
   *
   * `AlertDialog` is the package's component for exactly this and cannot be
   * suppressed by the browser, because it is ours.
   */
  async function remove(page: PageSummary) {
    setPendingDelete(null);
    setBusyId(page.id);
    setError(null);
    try {
      await deletePage(page.id);
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not delete that page.");
    } finally {
      setBusyId(null);
    }
  }

  async function copyLink(page: PageSummary) {
    if (!page.share_url) return;
    await navigator.clipboard.writeText(page.share_url);
    setCopiedId(page.id);
    window.setTimeout(() => setCopiedId(null), 2000);
  }

  // Memoised from `pages` rather than from a derived `all`, and declared ABOVE
  // the early return: a hook after a conditional return runs in a different
  // order on the loading render than on every later one, which is the one thing
  // React's hook model cannot tolerate.
  const all = useMemo(() => pages ?? [], [pages]);

  /**
   * Title and share link, case-insensitively.
   *
   * The link is searchable as well as the title because a teacher's way back to
   * a page is often the URL she handed out — she has it in a class message and
   * wants to know which page it is. The HTML body is deliberately NOT searched:
   * the list only holds summaries, so it would mean fetching every page.
   */
  const list = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return all.filter((page) => {
      if (filter === "published" && !page.published) return false;
      if (filter === "drafts" && page.published) return false;
      if (!needle) return true;
      return (
        page.title.toLowerCase().includes(needle) ||
        (page.share_url ?? "").toLowerCase().includes(needle)
      );
    });
  }, [all, query, filter]);

  /** Counts on the chips describe the WHOLE library, not the current search —
      a chip reading "Drafts (0)" because of the text in the box would be
      reporting on itself. */
  const counts = useMemo(
    () => ({
      all: all.length,
      published: all.filter((page) => page.published).length,
      drafts: all.filter((page) => !page.published).length,
    }),
    [all],
  );

  if (pages === null && !error) {
    return (
      <div className="flex justify-center p-12">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <Text variant="display" family="heading">
          Your lessons
        </Text>
        <Button onClick={() => navigate("/pages/new")} className="rounded-pill">New lesson</Button>
      </div>

      {error && (
        <div className="mb-4">
          <Alert.Root intent="danger">
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        </div>
      )}

      {/* Hidden until there is enough to be worth narrowing. One page and a
          search box is a control that only takes up room. */}
      {all.length > 3 && (
        <PagesFilterBar
          query={query}
          onQueryChange={setQuery}
          filter={filter}
          onFilterChange={setFilter}
          counts={counts}
        />
      )}

      {all.length === 0 ? (
        <Card.Root>
          <Card.Title>Nothing here yet</Card.Title>
          <Text tone="muted">
            Make a lesson, upload the files your program saved, then publish it
            to get a link you can give your students.
          </Text>
        </Card.Root>
      ) : list.length === 0 ? (
        <Card.Root>
          <Card.Title>Nothing matches</Card.Title>
          <Text tone="muted">
            {query.trim()
              ? "Try part of the title, or part of the share link."
              : "There are no pages in this filter yet."}
          </Text>
        </Card.Root>
      ) : (
        <div className="flex flex-col gap-3">
          {list.map((page) => (
            <Card.Root key={page.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Link to={`/pages/${page.id}`} className="no-underline">
                      <Text variant="title">{page.title}</Text>
                    </Link>
                    <Badge intent={page.published ? "success" : "neutral"}>
                      {page.published ? "Published" : "Draft"}
                    </Badge>
                  </div>
                  <Text variant="caption" tone="muted">
                    {page.file_count === 0
                      ? "No files uploaded yet"
                      : `${page.file_count} file${page.file_count === 1 ? "" : "s"}`}
                    {" · updated "}
                    {new Date(page.updated_at).toLocaleString()}
                  </Text>
                  {page.share_url && (
                    <div className="mt-1 break-all">
                      <Text variant="caption" tone="muted">
                        {page.share_url}
                      </Text>
                    </div>
                  )}
                </div>

                <div className="flex flex-wrap gap-2">
                  {page.share_url && (
                    <Button intent="secondary" size="sm" onClick={() => void copyLink(page)} className="rounded-pill">
                      {copiedId === page.id ? "Copied" : "Copy link"}
                    </Button>
                  )}
                  <Button
                    intent="secondary"
                    size="sm"
                    disabled={busyId === page.id}
                    onClick={() => void togglePublished(page)} className="rounded-pill">
                    {page.published ? "Withdraw" : "Publish"}
                  </Button>
                  <Button
                    intent="ghost"
                    size="sm"
                    disabled={busyId === page.id}
                    onClick={() => setPendingDelete(page)} className="rounded-pill">
                    Delete
                  </Button>
                </div>
              </div>
            </Card.Root>
          ))}
        </div>
      )}

      <AlertDialog.Root
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
      >
        <AlertDialog.Backdrop />
        <AlertDialog.Popup>
          <AlertDialog.Title>Delete “{pendingDelete?.title}”?</AlertDialog.Title>
          <AlertDialog.Description>
            {pendingDelete?.published
              ? "This page is published, so any student who already has the link will lose it. This cannot be undone."
              : "This cannot be undone."}
          </AlertDialog.Description>
          <div className="mt-4 flex justify-end gap-2">
            {/* `AlertDialog.Close` IS the button — it renders its own
                `<button>` and closes on click. Wrapping a `<Button>` inside it
                nests one button in another, which is invalid HTML and which
                React reports as a hydration error. Style the Close itself. */}
            <AlertDialog.Close className="border-line hover:bg-surface-alt text-ink cursor-pointer rounded-pill border px-4 py-2 text-sm font-medium">
              Keep it
            </AlertDialog.Close>
            <Button
              intent="danger"
              onClick={() => {
                if (pendingDelete) void remove(pendingDelete);
              }} className="rounded-pill">
              Delete
            </Button>
          </div>
        </AlertDialog.Popup>
      </AlertDialog.Root>
    </div>
  );
}
