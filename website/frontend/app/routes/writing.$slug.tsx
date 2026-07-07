import { Link } from "react-router";
import type { LoaderFunctionArgs, MetaFunction } from "react-router";

import { SiteLayout } from "~/components/SiteLayout";
import { getPost } from "~/lib/content.server";
import { seo } from "~/lib/seo";

export function loader({ params }: LoaderFunctionArgs) {
  const post = getPost(params.slug ?? "");
  if (!post) {
    throw new Response("Post not found", { status: 404 });
  }
  return { post };
}

export const meta: MetaFunction<typeof loader> = ({ data }) => {
  if (!data) return seo({ title: "Not found", description: "This post could not be found." });
  return seo({
    title: data.post.title,
    description: data.post.description,
    path: `/writing/${data.post.slug}`,
    image: data.post.ogImage,
    type: "article",
  });
};

/** Turn a YouTube watch/short URL into an embeddable URL, or null. */
function youtubeEmbed(url?: string): string | null {
  if (!url) return null;
  const match = url.match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|embed\/|shorts\/))([\w-]{11})/);
  return match ? `https://www.youtube.com/embed/${match[1]}` : null;
}

export default function WritingPost({ loaderData }: { loaderData: { post: ReturnType<typeof getPost> } }) {
  const post = loaderData.post!;
  const embed = youtubeEmbed(post.videoUrl);

  return (
    <SiteLayout>
      <article className="mx-auto max-w-3xl px-6 py-20">
        <Link to="/writing" className="text-sm font-medium text-accent hover:underline">
          ← All writing
        </Link>
        <p className="mt-8 text-xs uppercase tracking-wide text-muted">
          {post.date} · {post.readingMinutes} min read
        </p>
        <h1 className="mt-2 font-heading text-4xl font-semibold leading-tight text-ink">{post.title}</h1>
        <p className="mt-4 text-lg text-muted">{post.description}</p>

        {embed ? (
          <div className="mt-8 aspect-video overflow-hidden rounded-lg border border-line">
            <iframe
              title={post.title}
              src={embed}
              className="h-full w-full"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
        ) : post.videoUrl ? (
          <a
            href={post.videoUrl}
            className="mt-6 inline-block font-medium text-accent hover:underline"
            target="_blank"
            rel="noreferrer"
          >
            Watch the video →
          </a>
        ) : null}

        <div className="article mt-10" dangerouslySetInnerHTML={{ __html: post.html }} />
      </article>
    </SiteLayout>
  );
}
