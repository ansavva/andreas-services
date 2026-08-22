import { Route, Routes } from "react-router-dom";

import { BrowsePage } from "./pages/BrowsePage";
import { LegacyRedirect } from "./pages/LegacyRedirect";

/**
 * Three routes, and the third is a bridge.
 *
 * `/f/<node_id>` and `/o/<node_id>` are canonical (#313): the URL names a node
 * by id, so a share link outlives the rename or move that used to invalidate it.
 * `/` is the library root, whose id nothing knows before the first request.
 *
 * `*` is every URL studio handed out before that — the S3 key, spelled
 * `/projects/<project>/runs/…/output/clip.mp4` — and it goes to `LegacyRedirect`,
 * which asks the API what the path names and replaces itself with the id URL.
 * Matching those by *exclusion* is what reserves `/f/` and `/o/`; see
 * `utils/location`.
 *
 * Separate from `App` so the table can be exercised without the auth stack: the
 * gate renders a "not configured" notice when no user pool is set, which in a
 * test is every route resolving to the same thing. What the tests here assert is
 * which component a URL reaches, and that is this file and nothing else.
 *
 * Two things outside it have to agree. CloudFront's viewer-request function must
 * send all of these to `index.html` — including the legacy ones ending in
 * `.mp4`, which is why it routes by location rather than by extension
 * (`infra/modules/hosting`). And sign-out sends the user to `/`.
 */
export function StudioRoutes() {
  return (
    <Routes>
      <Route path="/" element={<BrowsePage />} />
      <Route path="/f/:nodeId" element={<BrowsePage />} />
      <Route path="/o/:nodeId" element={<BrowsePage />} />
      <Route path="*" element={<LegacyRedirect />} />
    </Routes>
  );
}
