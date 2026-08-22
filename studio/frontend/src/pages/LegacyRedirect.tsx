import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Alert, Button, Spinner } from "@ansavva/design-system";

import { resolvePath } from "../apis/studio";
import { folderPath, legacyPath, objectPath, ROOT_PATH } from "../utils/location";

/**
 * An old key-shaped share link, turned into the id URL it now means.
 *
 * Studio's URLs were the S3 key — `/projects/<project>/runs/…/output/clip.mp4` —
 * and every link anyone has ever sent, bookmarked or pasted into a message is
 * one of those. #313 made the id canonical, which would have broken all of them,
 * so this catches what the id routes do not match and asks `GET /api/resolve`
 * what the path names.
 *
 * **Once, and then it is gone.** The redirect `replace`s, so the old URL does
 * not stay in history: leaving it there makes back re-enter this component,
 * resolve again and push forward again, which is a back button that cannot
 * escape. The search string rides along, because `?sort=` is part of what was
 * shared.
 *
 * **The node's `kind` decides which route, not the trailing slash.** The old
 * scheme distinguished a folder from an object by a trailing `/`, the way S3
 * does. The catalog answers it outright, so a link that lost its slash on the
 * way through a chat client still lands on the right page.
 *
 * **A failure is shown, not swallowed.** A link that resolves to nothing is a
 * link somebody is holding that no longer works, and quietly landing them on the
 * root would make it look like it did. It is also the piece whose test exercises
 * the whole route table (`LegacyRedirect.test.tsx` renders `StudioRoutes`),
 * because nothing else in this app is a promise made to URLs written before it
 * existed.
 */
export function LegacyRedirect() {
  const location = useLocation();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  const path = useMemo(() => legacyPath(location.pathname), [location.pathname]);

  useEffect(() => {
    let cancelled = false;
    setError(null);

    resolvePath(path)
      .then((node) => {
        if (cancelled) return;
        const pathname = node.kind === "folder" ? folderPath(node.id) : objectPath(node.id);
        navigate({ pathname, search: location.search }, { replace: true });
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });

    return () => {
      cancelled = true;
    };
  }, [location.search, navigate, path]);

  if (error === null) {
    return (
      <div className="flex min-h-full items-center justify-center">
        <Spinner size="lg" label="Finding that link" />
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-full w-full max-w-2xl items-center justify-center p-6">
      <div className="flex w-full flex-col gap-3">
        <Alert.Root intent="danger">
          <Alert.Title>That link does not lead anywhere</Alert.Title>
          <Alert.Description>
            {/* The API's 404 names the first segment that was missing, which is
                the difference between "no such thing" and pointing at the folder
                the typo is in. Worth showing verbatim. */}
            Nothing in this library is at {path || "/"} — {error}. It may have been renamed,
            moved or deleted.
          </Alert.Description>
        </Alert.Root>
        <div>
          <Button size="sm" onClick={() => navigate(ROOT_PATH, { replace: true })}>
            Go to the library
          </Button>
        </div>
      </div>
    </div>
  );
}
