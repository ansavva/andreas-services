import type { ReactNode } from 'react';
import {
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  isRouteErrorResponse,
  useLoaderData,
  type LinksFunction,
} from 'react-router';

import faviconUrl from './assets/favicon.png?url';
import { AuthProvider } from '../src/context/AuthContext';
import { ProfileProvider } from '../src/context/ProfileContext';
import stylesheet from '../src/styles.css?url';

export function loader() {
  return {
    auth: {
      region: process.env.COGNITO_REGION ?? import.meta.env.VITE_AWS_REGION ?? 'us-east-1',
      userPoolId: process.env.COGNITO_USER_POOL_ID ?? import.meta.env.VITE_COGNITO_USER_POOL_ID ?? '',
      userPoolClientId: process.env.COGNITO_CLIENT_ID ?? import.meta.env.VITE_COGNITO_CLIENT_ID ?? '',
    },
  };
}

export const links: LinksFunction = () => [
  { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
  { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossOrigin: 'anonymous' },
  {
    rel: 'stylesheet',
    href: 'https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=Spectral:wght@500;600;700&display=swap',
  },
  { rel: 'icon', type: 'image/png', href: faviconUrl },
  { rel: 'stylesheet', href: stylesheet },
];

export function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" content="#1d5545" />
        <Meta />
        <Links />
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
  const { auth } = useLoaderData<typeof loader>();
  return (
    <AuthProvider config={auth}>
      <ProfileProvider>
        <Outlet />
      </ProfileProvider>
    </AuthProvider>
  );
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
