/** Build a consistent set of title/description/OG/Twitter meta descriptors. */
export interface SeoInput {
  title: string;
  description: string;
  path?: string;
  image?: string;
  type?: "website" | "article";
}

const SITE = "Andreas Services";
const ORIGIN = "https://www.andreas.services";

export function seo({ title, description, path = "/", image, type = "website" }: SeoInput) {
  const fullTitle = path === "/" ? title : `${title} · ${SITE}`;
  const url = `${ORIGIN}${path}`;
  const meta: Array<Record<string, string>> = [
    { title: fullTitle },
    { name: "description", content: description },
    { property: "og:title", content: fullTitle },
    { property: "og:description", content: description },
    { property: "og:type", content: type },
    { property: "og:url", content: url },
    { property: "og:site_name", content: SITE },
    { name: "twitter:card", content: image ? "summary_large_image" : "summary" },
    { name: "twitter:title", content: fullTitle },
    { name: "twitter:description", content: description },
    { tagName: "link", rel: "canonical", href: url },
  ];
  if (image) {
    meta.push({ property: "og:image", content: image });
    meta.push({ name: "twitter:image", content: image });
  }
  return meta;
}
