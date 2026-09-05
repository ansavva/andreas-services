import { index, route, type RouteConfig } from '@react-router/dev/routes';

// Paths the product app owns now. They stay registered here so links and
// invitation emails sent before the split keep resolving on this host; see
// legacy-redirect.ts.
const legacy = (path: string, id: string) => route(path, 'routes/legacy-redirect.ts', { id });

export default [
  index('routes/_index.tsx'),
  route('pricing', 'routes/pricing.tsx'),
  route('terms', 'routes/terms.tsx'),
  route('privacy', 'routes/privacy.tsx'),
  route('billing', 'routes/billing.tsx'),
  route('refunds', 'routes/refunds.tsx'),
  route('robots.txt', 'routes/robots[.]txt.ts'),
  route('sitemap.xml', 'routes/sitemap[.]xml.ts'),
  legacy('login', 'legacy-login'),
  legacy('join/:groupId', 'legacy-join'),
] satisfies RouteConfig;
