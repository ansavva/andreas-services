import type { ReactNode } from "react";
import {
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  isRouteErrorResponse,
  type LinksFunction,
  type LoaderFunctionArgs,
} from "react-router";

import { useTheme } from "./components/ThemeToggle";
import faviconUrl from "./assets/favicon.svg?url";
import { getTheme } from "./lib/theme.server";
import stylesheet from "./styles/app.css?url";

export async function loader({ request }: LoaderFunctionArgs) {
  return { theme: await getTheme(request) };
}

export const links: LinksFunction = () => [
  { rel: "preconnect", href: "https://fonts.googleapis.com" },
  { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
  {
    rel: "stylesheet",
    href: "https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&family=Spectral:wght@400;500;600;700&display=swap",
  },
  { rel: "icon", type: "image/svg+xml", href: faviconUrl },
  { rel: "stylesheet", href: stylesheet },
];

export function Layout({ children }: { children: ReactNode }) {
  const ga = import.meta.env.VITE_GA_MEASUREMENT_ID as string | undefined;
  const theme = useTheme();
  return (
    <html lang="en" data-theme={theme}>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <Meta />
        <Links />
        {ga ? (
          <>
            <script async src={`https://www.googletagmanager.com/gtag/js?id=${ga}`} />
            <script
              dangerouslySetInnerHTML={{
                __html: `window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','${ga}');`,
              }}
            />
          </>
        ) : null}
      </head>
      <body className="min-h-screen bg-bg font-body text-ink antialiased">
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
  const title = isRouteErrorResponse(error) ? `${error.status} ${error.statusText}` : "Something went wrong";
  const detail = isRouteErrorResponse(error)
    ? error.data
    : error instanceof Error
      ? error.message
      : "Unknown error";
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 px-6">
      <h1 className="font-heading text-4xl text-primary">{title}</h1>
      <p className="text-muted">{String(detail)}</p>
      <a href="/" className="text-accent underline">
        Back home
      </a>
    </main>
  );
}
