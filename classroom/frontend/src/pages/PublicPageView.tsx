import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Alert, Spinner, Text } from "@ansavva/design-system";

import { readPublicPage } from "../api";
import type { PublicPage } from "../api";

/**
 * What a student sees. No sign-in, no chrome beyond the title.
 *
 * `dangerouslySetInnerHTML` is correct here and is the point of the service:
 * the teacher authored this markup and it is meant to render. It is safe
 * because of the two layers described in the backend's `utils/html.py` — it was
 * sanitized on write, and the API serves it under a `script-src 'none'` CSP.
 * Never render unsanitized draft HTML this way; see `PageEditorPage`.
 */
export function PublicPageView() {
  const { slug } = useParams<{ slug: string }>();
  const [page, setPage] = useState<PublicPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    readPublicPage(slug)
      .then(setPage)
      .catch((err: unknown) =>
        setError(
          err instanceof Error ? err.message : "That page is not available.",
        ),
      );
  }, [slug]);

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-12">
        <Alert.Root intent="warning">
          <Alert.Title>Page not available</Alert.Title>
          <Alert.Description>
            This link may have been withdrawn by your teacher, or typed
            incorrectly.
          </Alert.Description>
        </Alert.Root>
      </div>
    );
  }

  if (!page) {
    return (
      <div className="flex justify-center p-12">
        <Spinner />
      </div>
    );
  }

  return (
    <article className="mx-auto max-w-3xl px-4 py-10">
      <Text variant="display" family="heading">
        {page.title}
      </Text>
      <div className="mt-6">
        <Text variant="caption" tone="muted">
          Updated {new Date(page.updated_at).toLocaleDateString()}
        </Text>
      </div>
      <div
        className="page-body mt-6"
        dangerouslySetInnerHTML={{ __html: page.html }}
      />
    </article>
  );
}
