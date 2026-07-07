import { Link } from "react-router";
import type { MetaFunction } from "react-router";

import { NewsletterForm } from "~/components/NewsletterForm";
import { SiteLayout } from "~/components/SiteLayout";
import { listPosts } from "~/lib/content.server";
import { seo } from "~/lib/seo";
import { SITE } from "~/lib/site";

export const meta: MetaFunction = () =>
  seo({
    title: "Andreas Services — AI automation that actually works",
    description:
      "Done-for-you AI automation consulting from an engineer who has shipped in the real world. Tell me what you’re trying to do; I’ll send a scoped quote in 48 hours — no sales pitch.",
    path: "/",
  });

export function loader() {
  return { posts: listPosts().slice(0, 3) };
}

const STEPS = [
  {
    title: "Tell me the problem",
    body: "One short brief — the task or workflow that’s eating your team’s time. No jargon required.",
  },
  {
    title: "I scope it in 48 hours",
    body: "You get a concrete plan and a fixed quote. If AI isn’t the right tool, I’ll tell you that too.",
  },
  {
    title: "I build it",
    body: "A working automation wired into the tools you already use — not a slide deck about the future.",
  },
];

export default function Home({ loaderData }: { loaderData: { posts: ReturnType<typeof listPosts> } }) {
  const { posts } = loaderData;
  return (
    <SiteLayout>
      {/* Hero */}
      <section className="mx-auto max-w-4xl px-6 pb-16 pt-20 sm:pt-28">
        <p className="text-sm font-medium uppercase tracking-wide text-accent">AI automation consulting</p>
        <h1 className="mt-4 font-heading text-4xl font-semibold leading-tight text-ink sm:text-5xl">
          A lot of the AI advice out there skips the part that actually matters — because it comes from
          people who’ve never had to make it work in the real world.{" "}
          <span className="text-primary">I have.</span>
        </h1>
        <p className="mt-6 max-w-2xl text-lg text-muted">
          I build the automations that quietly save your team hours every week — and I do it in public, so
          you can see exactly how the work gets done.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-4">
          <Link
            to="/services"
            className="inline-flex items-center whitespace-nowrap rounded-md bg-primary px-6 py-3 font-medium text-primary-text transition-colors hover:bg-primary-hover"
          >
            Get a scoped quote
          </Link>
          <a href="#newsletter" className="font-medium text-accent underline-offset-4 hover:underline">
            Read the newsletter
          </a>
        </div>
      </section>

      {/* Credibility bar */}
      <section className="border-y border-line bg-surface-alt/40">
        <p className="mx-auto max-w-6xl px-6 py-4 text-center text-sm font-medium text-muted">
          {SITE.credibility}
        </p>
      </section>

      {/* The problem you solve — speaking to "Sam" */}
      <section className="mx-auto max-w-3xl px-6 py-20">
        <h2 className="font-heading text-3xl font-semibold text-ink">You tried ChatGPT. It was… fine.</h2>
        <div className="mt-6 space-y-4 text-lg text-muted">
          <p>
            You know AI is supposed to change how your business runs. You’ve poked at it, got a few
            mediocre results, and quietly wondered whether you’re already behind.
          </p>
          <p>
            The problem isn’t you. Most of the loudest AI voices are selling a feeling, not a system —
            and a chat window is not an automation. The gap between “I asked the AI” and “this runs on
            its own every day” is exactly where I work.
          </p>
        </div>
      </section>

      {/* Services — 3-step */}
      <section className="border-t border-line bg-surface-alt/30">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <h2 className="font-heading text-3xl font-semibold text-ink">How working together works</h2>
          <div className="mt-10 grid gap-8 sm:grid-cols-3">
            {STEPS.map((step, i) => (
              <div key={step.title} className="rounded-lg border border-line bg-card p-6">
                <span className="font-heading text-3xl text-accent">{i + 1}</span>
                <h3 className="mt-3 font-heading text-xl text-primary">{step.title}</h3>
                <p className="mt-2 text-sm text-muted">{step.body}</p>
              </div>
            ))}
          </div>
          <div className="mt-10">
            <Link
              to="/services"
              className="inline-flex items-center whitespace-nowrap rounded-md bg-primary px-6 py-3 font-medium text-primary-text transition-colors hover:bg-primary-hover"
            >
              See the offer
            </Link>
          </div>
        </div>
      </section>

      {/* Writing teaser */}
      {posts.length > 0 ? (
        <section className="mx-auto max-w-6xl px-6 py-20">
          <div className="flex items-end justify-between">
            <h2 className="font-heading text-3xl font-semibold text-ink">Latest writing</h2>
            <Link to="/writing" className="text-sm font-medium text-accent hover:underline">
              All posts →
            </Link>
          </div>
          <div className="mt-8 grid gap-6 sm:grid-cols-3">
            {posts.map((post) => (
              <Link
                key={post.slug}
                to={`/writing/${post.slug}`}
                className="group rounded-lg border border-line bg-card p-6 transition-colors hover:border-accent"
              >
                <p className="text-xs uppercase tracking-wide text-muted">{post.date}</p>
                <h3 className="mt-2 font-heading text-lg text-ink group-hover:text-primary">{post.title}</h3>
                <p className="mt-2 line-clamp-3 text-sm text-muted">{post.description}</p>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      {/* Newsletter */}
      <section id="newsletter" className="border-t border-line bg-primary/5">
        <div className="mx-auto max-w-2xl px-6 py-20 text-center">
          <h2 className="font-heading text-3xl font-semibold text-ink">
            The half of AI that actually pays
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-muted">
            One practical email on using AI in a real business — the parts the influencers skip. No hype,
            no fluff.
          </p>
          <div className="mx-auto mt-8 max-w-md">
            <NewsletterForm compact />
          </div>
        </div>
      </section>
    </SiteLayout>
  );
}
