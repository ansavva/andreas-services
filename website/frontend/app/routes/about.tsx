import { Link } from "react-router";
import type { MetaFunction } from "react-router";

import { SiteLayout } from "~/components/SiteLayout";
import { seo } from "~/lib/seo";

export const meta: MetaFunction = () =>
  seo({
    title: "About",
    description:
      "An engineer of 12+ years and former Senior Development Manager, building practical AI automation in public — and teaching the half that actually pays.",
    path: "/about",
  });

export default function About() {
  return (
    <SiteLayout>
      <article className="mx-auto max-w-3xl px-6 py-20">
        <h1 className="font-heading text-4xl font-semibold text-ink sm:text-5xl">About</h1>

        <div className="mt-8 space-y-6 text-lg text-muted">
          <p>
            I’m Andreas — a software engineer of twelve-plus years and a former Senior Development
            Manager. I’ve spent my career shipping software that real people depend on, which means I’ve
            also spent it learning where the shiny demo ends and the hard part begins.
          </p>
          <p>
            That gap is why I started Andreas Services. A lot of the loudest AI advice comes from people
            who’ve never had to make a system work under real constraints — real data, real edge cases,
            real users who notice when it breaks. I have. So I build the automations that survive contact
            with an actual business, and I show the work as I go.
          </p>

          <h2 className="pt-4 font-heading text-2xl text-primary">What I believe about AI</h2>
          <p>
            AI is the most useful tool I’ve had in my career — and the most over-sold. The hype isn’t the
            enemy because it’s loud; it’s the enemy because it wastes your time and quietly convinces
            capable people they’re behind. The truth is calmer: a handful of well-built automations,
            aimed at the right workflows, compound fast.
          </p>
          <p>
            My whole approach is “bridge-based” — take what genuinely works, strip the mystique, and hand
            it over in a form you can use. On this site that shows up two ways: the consulting work, and a
            steady stream of writing and video that teaches the practical half most people skip.
          </p>
        </div>

        <div className="mt-12 flex flex-wrap gap-4">
          <Link
            to="/services"
            className="inline-flex items-center whitespace-nowrap rounded-md bg-primary px-6 py-3 font-medium text-primary-text transition-colors hover:bg-primary-hover"
          >
            Work with me
          </Link>
          <Link
            to="/writing"
            className="inline-flex items-center whitespace-nowrap rounded-md border border-line px-6 py-3 font-medium text-ink transition-colors hover:bg-surface-alt"
          >
            Read the writing
          </Link>
        </div>
      </article>
    </SiteLayout>
  );
}
