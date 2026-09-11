import type { ReactNode } from 'react';
import {
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  isRouteErrorResponse,
  type LinksFunction,
} from 'react-router';

import faviconUrl from './assets/favicon.png?url';
import stylesheet from '../src/styles.css?url';

export const links: LinksFunction = () => [
  { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
  { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossOrigin: 'anonymous' },
  {
    rel: 'stylesheet',
    href: 'https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;500;600;700&display=swap',
  },
  { rel: 'icon', type: 'image/png', href: faviconUrl },
  { rel: 'stylesheet', href: stylesheet },
];

/**
 * Turn the scheme on before the first paint.
 *
 * The design system's web leaves read `data-theme`, not `prefers-color-scheme`
 * — a media query alone reaches Humbugg's own custom properties and leaves every
 * package component on the light ones. So the attribute has to be set, and it
 * has to be set in a blocking script in `<head>`: this site is server-rendered,
 * so the HTML arrives with no attribute, and setting it from an effect would
 * paint the cream scheme first and flash.
 *
 * `humbugg:theme` in `localStorage` is an explicit override, written only by
 * the header's theme control (`src/components/ThemeToggle.tsx`) — read it
 * first, and when it names `light`/`dark`, paint that and stop: no OS
 * listener, because an explicit choice must not be clobbered by the system
 * changing underneath it. Anything else (no key, or `system`, which is never
 * actually written — see `src/theme.ts`) is today's behaviour unchanged: read
 * the OS query and keep listening for it to change.
 *
 * This mirrors `src/theme.ts`'s read half by hand rather than importing it —
 * it has to run as a blocking inline script before any module loads. There is
 * still no switch on the product app: the package's native leaves read
 * `useColorScheme()` with no override, so this key is marketing-only and the
 * app keeps following the OS regardless of what a visitor chose here.
 */
const APPLY_SCHEME = `(function(){
  try {
    var KEY = 'humbugg:theme';
    var set = function (dark) { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; };
    var stored = null;
    try { stored = window.localStorage.getItem(KEY); } catch (e) {}
    if (stored === 'light' || stored === 'dark') {
      set(stored === 'dark');
    } else {
      var q = window.matchMedia('(prefers-color-scheme: dark)');
      set(q.matches);
      q.addEventListener('change', function (e) { set(e.matches); });
    }
  } catch (e) {}
})();`;

export function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        {/* Tells the browser to paint its own furniture — scrollbars, form
            controls, the canvas behind the page — in whichever scheme is live. */}
        <meta name="color-scheme" content="light dark" />
        <meta name="theme-color" content="#fbf8ef" media="(prefers-color-scheme: light)" />
        <meta name="theme-color" content="#0e1f1a" media="(prefers-color-scheme: dark)" />
        <Meta />
        <Links />
        <script dangerouslySetInnerHTML={{ __html: APPLY_SCHEME }} />
      </head>
      <body>
        {children}
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

export default function App() {
  return <Outlet />;
}

export function ErrorBoundary({ error }: { error: unknown }) {
  const notFound = isRouteErrorResponse(error) && error.status === 404;
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center px-5 text-center">
      <p className="eyebrow">{notFound ? 'Page not found' : 'Something went wrong'}</p>
      <h1 className="mt-4 font-heading text-5xl font-semibold">
        {notFound ? 'That gift tag leads nowhere.' : 'Humbugg hit a snag.'}
      </h1>
      <p className="mt-5 text-muted">
        {notFound ? 'Return home and we’ll get you back to the exchange.' : 'Please refresh and try again.'}
      </p>
      <a className="mt-8 font-semibold text-primary hover:underline" href="/">Return to Humbugg</a>
    </main>
  );
}
