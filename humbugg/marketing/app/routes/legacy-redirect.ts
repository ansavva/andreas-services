import { redirect } from 'react-router';

import { appUrl } from '../../src/config/site';

/**
 * Paths this site served before the product moved to `app.humbugg.com`, kept
 * alive as permanent redirects: invitation emails already in the wild point at
 * `humbugg.com/join/:groupId`. The path is identical on both hosts, so only the
 * origin changes. The `#invite=<secret>` fragment never reaches the server — the
 * browser reattaches it to the redirect target — which is why the path is
 * forwarded as received and never rebuilt from parts.
 *
 * One module backs several route entries; `routes.ts` gives each its own `id`.
 */
export function loader({ request }: { request: Request }) {
  const { pathname, search } = new URL(request.url);
  return redirect(`${appUrl(pathname)}${search}`, 301);
}
