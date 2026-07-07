/**
 * Companion-blog engine. Each post is a markdown file with frontmatter that
 * pairs a written article with its source video. Content is bundled into the
 * server build at compile time via Vite's import.meta.glob, so publishing a
 * post is just adding a file under app/content/writing/.
 */
import matter from "gray-matter";
import { marked } from "marked";

export interface PostMeta {
  slug: string;
  title: string;
  date: string;
  description: string;
  videoUrl?: string;
  ogImage?: string;
  readingMinutes: number;
}

export interface Post extends PostMeta {
  html: string;
}

// Raw markdown for every companion post, keyed by file path.
const files = import.meta.glob("../content/writing/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

function slugFromPath(path: string): string {
  return path.split("/").pop()!.replace(/\.md$/, "");
}

function parse(path: string, raw: string): Post {
  const { data, content } = matter(raw);
  const words = content.trim().split(/\s+/).length;
  return {
    slug: slugFromPath(path),
    title: String(data.title ?? "Untitled"),
    date: String(data.date ?? ""),
    description: String(data.description ?? ""),
    videoUrl: data.videoUrl ? String(data.videoUrl) : undefined,
    ogImage: data.ogImage ? String(data.ogImage) : undefined,
    readingMinutes: Math.max(1, Math.round(words / 200)),
    html: marked.parse(content, { async: false }) as string,
  };
}

const posts: Post[] = Object.entries(files)
  .map(([path, raw]) => parse(path, raw))
  .sort((a, b) => (a.date < b.date ? 1 : -1));

export function listPosts(): PostMeta[] {
  // Drop the rendered HTML from the list view.
  return posts.map(({ html: _html, ...meta }) => meta);
}

export function getPost(slug: string): Post | null {
  return posts.find((p) => p.slug === slug) ?? null;
}
