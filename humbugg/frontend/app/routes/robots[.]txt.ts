import { canonicalUrl } from '../../src/config/site';

export function loader() {
  return new Response(`User-agent: *\nAllow: /\nDisallow: /app\nDisallow: /confirm\nDisallow: /forgot-password\nSitemap: ${canonicalUrl('/sitemap.xml')}\n`, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
