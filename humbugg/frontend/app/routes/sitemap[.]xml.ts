import { canonicalUrl } from '../../src/config/site';

export function loader() {
  const updated = new Date().toISOString().slice(0, 10);
  return new Response(`<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>${canonicalUrl('/')}</loc><lastmod>${updated}</lastmod><changefreq>monthly</changefreq><priority>1.0</priority></url>
  <url><loc>${canonicalUrl('/signup')}</loc><lastmod>${updated}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>
</urlset>`, {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
}
