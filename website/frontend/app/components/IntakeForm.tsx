import { Button } from "@ansavva/design-system";
import { useFetcher } from "react-router";

interface ActionResult {
  ok?: boolean;
  error?: string;
}

const inputClass =
  "h-11 w-full rounded-md border border-line bg-card px-3 text-sm text-ink placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg";

const labelClass = "text-sm font-medium text-ink";

/** Primary conversion mechanism: "scoped quote in 48 hours, no sales pitch".
 *  Posts to the /api/intake resource route. */
export function IntakeForm({ sourcePage = "/services" }: { sourcePage?: string }) {
  const fetcher = useFetcher<ActionResult>();
  const submitting = fetcher.state !== "idle";

  if (fetcher.data?.ok) {
    return (
      <div className="rounded-lg border border-line bg-surface-alt/50 p-6">
        <p className="font-heading text-xl text-primary">Got it — talk soon.</p>
        <p className="mt-2 text-sm text-muted">
          I read every one of these myself. You’ll hear back with a scoped quote within 48 hours.
        </p>
      </div>
    );
  }

  return (
    <fetcher.Form method="post" action="/api/intake" className="flex flex-col gap-4">
      <input type="hidden" name="source_page" value={sourcePage} />
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5">
          <span className={labelClass}>Name</span>
          <input name="name" autoComplete="name" className={inputClass} placeholder="Sam" />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className={labelClass}>
            Email <span className="text-danger">*</span>
          </span>
          <input
            type="email"
            name="email"
            required
            autoComplete="email"
            className={inputClass}
            placeholder="sam@company.com"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className={labelClass}>Company</span>
          <input name="company" autoComplete="organization" className={inputClass} placeholder="Acme Co." />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className={labelClass}>Rough budget</span>
          <input name="budget" className={inputClass} placeholder="Not sure yet" />
        </label>
      </div>
      <label className="flex flex-col gap-1.5">
        <span className={labelClass}>
          What are you trying to do? <span className="text-danger">*</span>
        </span>
        <textarea
          name="message"
          required
          rows={5}
          className={`${inputClass} h-auto resize-y py-2`}
          placeholder="The task or workflow you want to automate, and what “done” looks like."
        />
      </label>

      {fetcher.data?.error ? <p className="text-sm text-danger">{fetcher.data.error}</p> : null}

      <div className="flex items-center gap-4">
        <Button type="submit" intent="primary" size="lg" disabled={submitting}>
          {submitting ? "Sending…" : "Get a scoped quote"}
        </Button>
        <span className="text-xs text-muted">48-hour turnaround · no sales pitch</span>
      </div>
    </fetcher.Form>
  );
}
