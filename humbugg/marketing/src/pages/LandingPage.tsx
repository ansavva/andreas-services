import { Button, buttonClass } from '@ansavva/design-system';
import { useSearchParams } from 'react-router';

import { Shell } from '../components/Layout';
import { appUrl, canonicalUrl } from '../config/site';

export default function LandingPage() {
  const [searchParams] = useSearchParams();
  const accountDeleted = searchParams.get('account_deleted') === '1';
  return (
    <Shell compact>
      {accountDeleted && (
        <div role="status" className="border-b border-line bg-surface-alt px-5 py-4 text-center text-sm font-medium text-ink lg:px-8">
          Your account was deleted. We're sorry to see you go — you're welcome back anytime.
        </div>
      )}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'WebApplication',
            name: 'Humbugg',
            url: canonicalUrl('/'),
            applicationCategory: 'LifestyleApplication',
            operatingSystem: 'Web',
            offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
            description: 'A private, self-service Secret Santa group organizer.',
          }),
        }}
      />
      <section className="hero-grid overflow-hidden border-b border-line">
        <div className="mx-auto grid min-h-[680px] max-w-7xl items-center gap-12 px-5 py-20 lg:grid-cols-[1.1fr_.9fr] lg:px-8">
          <div className="max-w-3xl">
            <p className="eyebrow">Secret Santa, minus the group-chat chaos</p>
            <h1 className="mt-5 font-heading text-5xl font-semibold leading-[1.02] tracking-[-.04em] text-ink sm:text-7xl">
              More wonder.<br /><span className="text-primary">Less wrangling.</span>
            </h1>
            <p className="mt-7 max-w-2xl text-lg leading-8 text-muted sm:text-xl">
              Bring everyone together, collect wish lists, set thoughtful exclusions, and make a private draw in one calm place.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <a className={buttonClass({ size: 'lg' })} href={appUrl('/login')}>Create your exchange</a>
              <Button size="lg" intent="secondary" onClick={() => document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' })}>See how it works</Button>
            </div>
            <p className="mt-5 text-sm text-muted">Free to use · No credit card · Private assignments</p>
          </div>
          <div className="relative mx-auto w-full max-w-lg" aria-label="A Humbugg exchange ready to draw">
            <div className="hero-card hero-card-back" />
            <div className="hero-card relative z-10">
              <div className="flex items-start justify-between border-b border-line pb-5">
                <div><p className="eyebrow">This year’s exchange</p><h2 className="mt-2 font-heading text-3xl font-semibold">The Holly Jolly Crew</h2></div>
                <span className="rounded-pill bg-surface-alt px-3 py-1 text-xs font-semibold text-primary">Ready</span>
              </div>
              <div className="my-7 space-y-3">
                {['Maya', 'Theo', 'Nina', 'Sam', 'Alex'].map((name, index) => (
                  <div key={name} className="flex items-center gap-3 rounded-md bg-surface-alt px-4 py-3">
                    <span className="avatar-chip">{name[0]}</span><span className="font-medium">{name}</span>
                    <span className="ml-auto text-xs text-muted">{index < 4 ? 'Wish list ready' : 'Joined'}</span>
                  </div>
                ))}
              </div>
              <div className="rounded-md bg-primary p-4 text-center font-semibold text-primary-text">5 people · Ready to draw</div>
            </div>
          </div>
        </div>
      </section>

      <section id="how-it-works" className="mx-auto max-w-7xl px-5 py-24 lg:px-8">
        <div className="max-w-2xl"><p className="eyebrow">How it works</p><h2 className="mt-3 font-heading text-4xl font-semibold sm:text-5xl">From invite to exchange in three easy steps.</h2></div>
        <div className="mt-14 grid gap-6 md:grid-cols-3">
          {[
            ['01', 'Create your group', 'Choose a date and budget, then share one private invitation link.'],
            ['02', 'Make it thoughtful', 'Everyone adds gift ideas, avoidances, and an optional delivery address.'],
            ['03', 'Draw with confidence', 'Set pair exclusions, lock the group, and reveal one private recipient to each person.'],
          ].map(([number, title, text]) => (
            <article key={number} className="feature-card"><span className="step-number">{number}</span><h3 className="mt-8 font-heading text-2xl font-semibold">{title}</h3><p className="mt-3 leading-7 text-muted">{text}</p></article>
          ))}
        </div>
      </section>

      <section className="bg-primary text-primary-text">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-8 px-5 py-16 sm:flex-row sm:items-center lg:px-8">
          <div><p className="text-sm font-semibold uppercase tracking-[.2em] text-primary-text/70">Ready when you are</p><h2 className="mt-2 font-heading text-3xl font-semibold sm:text-4xl">Make this year’s exchange feel effortless.</h2></div>
          <a className={buttonClass({ intent: 'secondary', size: 'lg' })} href={appUrl('/login')}>Start your group</a>
        </div>
      </section>
    </Shell>
  );
}
