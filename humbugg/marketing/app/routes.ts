import { index, route, type RouteConfig } from '@react-router/dev/routes';

export default [
  index('routes/_index.tsx'),
  route('pricing', 'routes/pricing.tsx'),
  route('terms', 'routes/terms.tsx'),
  route('privacy', 'routes/privacy.tsx'),
  route('billing', 'routes/billing.tsx'),
  route('refunds', 'routes/refunds.tsx'),
  route('robots.txt', 'routes/robots[.]txt.ts'),
  route('sitemap.xml', 'routes/sitemap[.]xml.ts'),
] satisfies RouteConfig;
