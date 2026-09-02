import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, Badge, Button, Card, Spinner, Text } from "@ansavva/design-system";

import { deletePage, listPages, updatePage } from "../api";
import type { PageSummary } from "../api";

/** Everything the signed-in teacher has made, newest first. */
export function PagesListPage() {
  const navigate = useNavigate();
  const [pages, setPages] = useState<PageSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

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

  async function remove(page: PageSummary) {
    if (!window.confirm(`Delete "${page.title}"? Students with the link will lose it.`)) {
      return;
    }
    setBusyId(page.id);
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

  if (pages === null && !error) {
    return (
      <div className="flex justify-center p-12">
        <Spinner />
      </div>
    );
  }

  const list = pages ?? [];

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <Text variant="display" family="heading">
          Your pages
        </Text>
        <Button onClick={() => navigate("/pages/new")}>New page</Button>
      </div>

      {error && (
        <div className="mb-4">
          <Alert.Root intent="danger">
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        </div>
      )}

      {list.length === 0 ? (
        <Card.Root>
          <Card.Title>Nothing here yet</Card.Title>
          <Text tone="muted">
            Make a page for a warm-up, a worksheet or a study guide, then publish
            it to get a link you can give your students.
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
                    Updated {new Date(page.updated_at).toLocaleString()}
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
                    <Button intent="secondary" size="sm" onClick={() => void copyLink(page)}>
                      {copiedId === page.id ? "Copied" : "Copy link"}
                    </Button>
                  )}
                  <Button
                    intent="secondary"
                    size="sm"
                    disabled={busyId === page.id}
                    onClick={() => void togglePublished(page)}
                  >
                    {page.published ? "Withdraw" : "Publish"}
                  </Button>
                  <Button
                    intent="ghost"
                    size="sm"
                    disabled={busyId === page.id}
                    onClick={() => void remove(page)}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            </Card.Root>
          ))}
        </div>
      )}
    </div>
  );
}
