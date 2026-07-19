import { index, route, type RouteConfig } from '@react-router/dev/routes';

export default [
  index('routes/_index.tsx'),
  route('login', 'routes/login.tsx'),
  route('signup', 'routes/signup.tsx'),
  route('confirm', 'routes/confirm.tsx'),
  route('forgot-password', 'routes/forgot-password.tsx'),
  route('join/:groupId', 'routes/join.$groupId.tsx'),
  route('terms', 'routes/terms.tsx'),
  route('privacy', 'routes/privacy.tsx'),
  route('billing', 'routes/billing.tsx'),
  route('refunds', 'routes/refunds.tsx'),
  route('app', 'routes/app._index.tsx'),
  route('app/groups/:groupId', 'routes/app.groups.$groupId.tsx'),
  route('robots.txt', 'routes/robots[.]txt.ts'),
  route('sitemap.xml', 'routes/sitemap[.]xml.ts'),
] satisfies RouteConfig;
