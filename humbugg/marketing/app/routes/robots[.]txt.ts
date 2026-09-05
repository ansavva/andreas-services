import { canonicalUrl } from '../../src/config/site';

export function loader() {
  // The disallowed paths are the legacy product routes; they only redirect to
  // app.humbugg.com now, and there is nothing on this origin worth crawling.
  return new Response(`User-agent: *\nAllow: /\nDisallow: /join\nDisallow: /login\nSitemap: ${canonicalUrl('/sitemap.xml')}\n`, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
