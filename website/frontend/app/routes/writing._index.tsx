import { Link } from "react-router";
import type { MetaFunction } from "react-router";

import { SiteLayout } from "~/components/SiteLayout";
import { listPosts } from "~/lib/content.server";
import { seo } from "~/lib/seo";

export const meta: MetaFunction = () =>
  seo({
    title: "Writing",
    description:
      "Practical writing on using AI in a real business — each post the companion to a video. No hype, just the parts that pay.",
    path: "/writing",
  });

export function loader() {
  return { posts: listPosts() };
}

export default function WritingIndex({ loaderData }: { loaderData: { posts: ReturnType<typeof listPosts> } }) {
  const { posts } = loaderData;
  return (
    <SiteLayout>
      <section className="mx-auto max-w-3xl px-6 py-20">
        <h1 className="font-heading text-4xl font-semibold text-ink sm:text-5xl">Writing</h1>
        <p className="mt-4 text-lg text-muted">
          Every post is the written companion to a video — the practical half of AI, minus the hype.
        </p>

        {posts.length === 0 ? (
          <p className="mt-12 text-muted">First posts landing soon.</p>
        ) : (
          <ul className="mt-12 space-y-10">
            {posts.map((post) => (
              <li key={post.slug} className="border-b border-line pb-10">
                <p className="text-xs uppercase tracking-wide text-muted">
                  {post.date} · {post.readingMinutes} min read
                </p>
                <h2 className="mt-2 font-heading text-2xl text-ink">
                  <Link to={`/writing/${post.slug}`} className="hover:text-primary">
                    {post.title}
                  </Link>
                </h2>
                <p className="mt-2 text-muted">{post.description}</p>
                <Link
                  to={`/writing/${post.slug}`}
                  className="mt-3 inline-block text-sm font-medium text-accent hover:underline"
                >
                  Read →
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </SiteLayout>
  );
}
