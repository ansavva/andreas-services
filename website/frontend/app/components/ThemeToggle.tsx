import { useFetcher, useFetchers, useRouteLoaderData } from "react-router";

type Theme = "light" | "dark";

/** Current theme: optimistic pending value, else the root loader's cookie value. */
export function useTheme(): Theme {
  const rootData = useRouteLoaderData("root") as { theme?: Theme } | undefined;
  const pending = useFetchers().find((f) => f.formAction === "/api/theme");
  const optimistic = pending?.formData?.get("theme");
  if (optimistic === "light" || optimistic === "dark") return optimistic;
  return rootData?.theme ?? "light";
}

export function ThemeToggle() {
  const fetcher = useFetcher();
  const theme = useTheme();
  const next: Theme = theme === "dark" ? "light" : "dark";

  return (
    <fetcher.Form method="post" action="/api/theme" className="flex">
      <input type="hidden" name="theme" value={next} />
      <button
        type="submit"
        aria-label={`Switch to ${next} theme`}
        title={`Switch to ${next} theme`}
        className="grid h-9 w-9 place-items-center rounded-md text-muted transition-colors hover:bg-surface-alt hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
      >
        {theme === "dark" ? (
          // Sun — click to go light
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
          </svg>
        ) : (
          // Moon — click to go dark
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
          </svg>
        )}
      </button>
    </fetcher.Form>
  );
}
