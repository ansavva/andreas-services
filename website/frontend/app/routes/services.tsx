import type { MetaFunction } from "react-router";

import { IntakeForm } from "~/components/IntakeForm";
import { SiteLayout } from "~/components/SiteLayout";
import { CAL_LINK } from "~/lib/site";
import { seo } from "~/lib/seo";

export const meta: MetaFunction = () =>
  seo({
    title: "Work with me",
    description:
      "Done-for-you AI automation. Tell me what you’re trying to do and I’ll send a scoped, fixed quote within 48 hours — no sales pitch.",
    path: "/services",
  });

const GOOD_FIT = [
  "You run or manage a team drowning in a repetitive, rules-y workflow.",
  "You’ve tried ChatGPT and want the version that runs without you babysitting it.",
  "You want someone who can actually build it, not just advise on it.",
];

const NOT_FIT = [
  "You want a keynote or a “thought leadership” retainer.",
  "You’re looking for the cheapest freelancer, not the right outcome.",
  "The goal is hype for investors rather than hours saved.",
];

const FAQ = [
  {
    q: "How much does it cost?",
    a: "Every engagement is scoped and fixed-price. You’ll get the number before any work starts — no open-ended hourly surprises.",
  },
  {
    q: "What do I actually get?",
    a: "A working automation wired into your existing tools, plus a short handover so your team can run and trust it.",
  },
  {
    q: "What if AI isn’t the right tool?",
    a: "I’ll tell you. I’d rather lose a project than sell you an automation that shouldn’t exist.",
  },
];

export default function Services() {
  return (
    <SiteLayout>
      <section className="mx-auto max-w-4xl px-6 pb-12 pt-20">
        <h1 className="font-heading text-4xl font-semibold text-ink sm:text-5xl">Work with me</h1>
        <p className="mt-6 max-w-2xl text-lg text-muted">
          One offer, done properly: <strong className="text-ink">done-for-you AI automation</strong>. You
          tell me what you’re trying to do; I send back a scoped, fixed quote within 48 hours. No decks,
          no discovery-call maze, no sales pitch.
        </p>
      </section>

      {/* Fit / not fit */}
      <section className="mx-auto grid max-w-4xl gap-8 px-6 pb-16 sm:grid-cols-2">
        <div className="rounded-lg border border-line bg-card p-6">
          <h2 className="font-heading text-xl text-primary">This is for you if…</h2>
          <ul className="mt-4 space-y-3 text-sm text-muted">
            {GOOD_FIT.map((item) => (
              <li key={item} className="flex gap-2">
                <span className="text-accent">✓</span>
                {item}
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-lg border border-line bg-surface-alt/40 p-6">
          <h2 className="font-heading text-xl text-ink">It’s probably not a fit if…</h2>
          <ul className="mt-4 space-y-3 text-sm text-muted">
            {NOT_FIT.map((item) => (
              <li key={item} className="flex gap-2">
                <span className="text-clay">—</span>
                {item}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Intake form */}
      <section className="border-t border-line bg-surface-alt/30">
        <div className="mx-auto max-w-3xl px-6 py-16">
          <h2 className="font-heading text-3xl font-semibold text-ink">Tell me what you’re trying to do</h2>
          <p className="mt-3 text-muted">
            The more concrete, the better. I read every submission myself.
          </p>
          <div className="mt-8">
            <IntakeForm sourcePage="/services" />
          </div>
        </div>
      </section>

      {/* Booking */}
      <section className="mx-auto max-w-3xl px-6 py-16">
        <h2 className="font-heading text-3xl font-semibold text-ink">Prefer to talk first?</h2>
        <p className="mt-3 text-muted">Grab a short intro call</p>
        <div className="mt-6 overflow-hidden rounded-lg border border-line">
          <iframe
            title="Book an intro call"
            src={`https://cal.com/${CAL_LINK}`}
            className="h-[640px] w-full"
            loading="lazy"
          />
        </div>
      </section>

      {/* FAQ */}
      <section className="mx-auto max-w-3xl px-6 pb-24">
        <h2 className="font-heading text-3xl font-semibold text-ink">Questions</h2>
        <dl className="mt-8 space-y-6">
          {FAQ.map((item) => (
            <div key={item.q} className="border-b border-line pb-6">
              <dt className="font-heading text-lg text-primary">{item.q}</dt>
              <dd className="mt-2 text-muted">{item.a}</dd>
            </div>
          ))}
        </dl>
      </section>
    </SiteLayout>
  );
}
