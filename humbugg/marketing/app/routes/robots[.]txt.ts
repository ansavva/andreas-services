import { canonicalUrl } from '../../src/config/site';

export function loader() {
  // Every path this origin serves is a public marketing page; the product lives
  // on app.humbugg.com and is not linked from here for crawling.
  return new Response(`User-agent: *\nAllow: /\nSitemap: ${canonicalUrl('/sitemap.xml')}\n`, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
