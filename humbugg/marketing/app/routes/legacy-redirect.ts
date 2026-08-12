import { redirect } from 'react-router';

import { appUrl, legacyAppPath } from '../../src/config/site';

/**
 * Every path this site served before the product moved to `app.humbugg.com`.
 * Invitation emails already in the wild point at `humbugg.com/join/:groupId`,
 * so these forward permanently rather than 404. The `#invite=<secret>` fragment
 * never reaches the server — the browser reattaches it to the redirect target —
 * which is why the path must be rewritten and never rebuilt from parts.
 *
 * One module backs several route entries; `routes.ts` gives each its own `id`.
 */
export function loader({ request }: { request: Request }) {
  const { pathname, search } = new URL(request.url);
  return redirect(`${appUrl(legacyAppPath(pathname))}${search}`, 301);
}
