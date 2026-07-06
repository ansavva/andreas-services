import { Button } from "@ansavva/design-system";
import { useFetcher } from "react-router";

interface ActionResult {
  ok?: boolean;
  error?: string;
}

/** Sitewide newsletter capture. Posts to the /api/subscribe resource route. */
export function NewsletterForm({ compact = false }: { compact?: boolean }) {
  const fetcher = useFetcher<ActionResult>();
  const submitting = fetcher.state !== "idle";
  const done = fetcher.data?.ok;

  if (done) {
    return (
      <p className="text-sm font-medium text-primary">
        You’re in. Check your inbox to confirm.
      </p>
    );
  }

  return (
    <fetcher.Form
      method="post"
      action="/api/subscribe"
      className={compact ? "flex flex-col gap-2 sm:flex-row" : "flex flex-col gap-3"}
    >
      <input
        type="email"
        name="email"
        required
        placeholder="you@company.com"
        aria-label="Email address"
        className="h-11 w-full rounded-md border border-line bg-card px-3 text-sm text-ink placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
      />
      <Button type="submit" intent="primary" disabled={submitting} className="shrink-0">
        {submitting ? "Joining…" : "Read the newsletter"}
      </Button>
      {fetcher.data?.error ? (
        <p className="text-sm text-danger sm:basis-full">{fetcher.data.error}</p>
      ) : null}
    </fetcher.Form>
  );
}
