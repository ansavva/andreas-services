import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Inbox, Mail, RefreshCw } from "lucide-react";
import type { ProcessedEmail } from "@/types";
import { useAdminApi } from "@/hooks/useAdminApi";
import { useAuth } from "@/context/AuthContext";
import { SkeletonCard } from "@/components/SkeletonCard";

function formatTs(isoStr: string): string {
  if (!isoStr) return "—";
  try {
    return new Date(isoStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

function formatEmailDate(rfcStr: string): string {
  if (!rfcStr) return "—";
  try {
    return new Date(rfcStr).toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return rfcStr;
  }
}

function stripName(sender: string): string {
  const match = sender.match(/^(.+?)\s*<[^>]+>/);
  return match ? match[1].trim() : sender;
}

function EmailRow({ email }: { email: ProcessedEmail }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="theme-transition border border-[var(--color-border)] rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-[var(--color-border)] transition-colors"
      >
        <span className="text-[var(--color-text-muted)] flex-shrink-0">
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </span>

        <Mail size={16} className="text-[var(--color-primary)] flex-shrink-0" />

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-[var(--color-text-primary)] truncate">
            {email.email_subject || "(no subject)"}
          </p>
          <p className="text-xs text-[var(--color-text-muted)] truncate">
            {stripName(email.email_sender)}
          </p>
        </div>

        <div className="flex-shrink-0 text-right hidden sm:block">
          <p className="text-xs text-[var(--color-text-muted)]">
            {formatEmailDate(email.source_email_date)}
          </p>
          <p className="text-xs text-[var(--color-text-muted)]">
            processed {formatTs(email.processed_at)}
          </p>
        </div>

        <span className="flex-shrink-0 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-[var(--color-badge)] text-[var(--color-badge-text)]">
          {email.event_count} {email.event_count === 1 ? "event" : "events"}
        </span>
      </button>

      {expanded && (
        <div className="px-4 pb-3 pt-1 border-t border-[var(--color-border)] bg-[var(--color-background)]">
          <div className="sm:hidden text-xs text-[var(--color-text-muted)] mb-2">
            <span>Received: {formatEmailDate(email.source_email_date)}</span>
            {" · "}
            <span>Processed: {formatTs(email.processed_at)}</span>
          </div>
          <p className="text-xs text-[var(--color-text-muted)] mb-1">
            <span className="font-medium">From:</span> {email.email_sender}
          </p>
          <p className="text-xs text-[var(--color-text-muted)]">
            <span className="font-medium">Gmail ID:</span>{" "}
            <span className="font-mono">{email.email_id}</span>
          </p>
          {email.image_url && (
            <p className="text-xs text-[var(--color-text-muted)] mt-1 truncate">
              <span className="font-medium">Image:</span>{" "}
              <a
                href={email.image_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[var(--color-primary)] hover:underline"
              >
                {email.image_url}
              </a>
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function AdminEmailsSection() {
  const api = useAdminApi();
  const { idToken } = useAuth();
  const [emails, setEmails] = useState<ProcessedEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [runMessage, setRunMessage] = useState<string | null>(null);

  const fetchEmails = useCallback(async () => {
    if (!idToken) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.listAdminEmails();
      setEmails(data.emails ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [api, idToken]);

  useEffect(() => {
    void fetchEmails();
  }, [fetchEmails]);

  const runProcessor = useCallback(async () => {
    setRunning(true);
    setRunError(null);
    setRunMessage(null);
    try {
      await api.triggerEmailProcessor();
      setRunMessage(
        "Processing started — new emails will appear here shortly. Refreshing in a minute."
      );
      // The run is asynchronous (up to ~5 min), so give it a head start
      // before reloading the list.
      window.setTimeout(() => void fetchEmails(), 60_000);
    } catch (err) {
      setRunError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setRunning(false);
    }
  }, [api, fetchEmails]);

  return (
    <div>
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Processed emails</h3>
          <p className="text-xs text-[var(--color-text-muted)]">
            Emails Scout has fetched and extracted events from.
          </p>
        </div>

        <button
          onClick={() => void runProcessor()}
          disabled={running}
          title="Fetch new emails and extract events now"
          className="flex-shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-3 py-2 text-sm font-medium text-white transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw size={15} className={running ? "animate-spin" : ""} />
          {running ? "Starting…" : "Run email processor now"}
        </button>
      </div>

      {runMessage && (
        <div className="mb-4 rounded-lg border border-green-300 bg-green-50 dark:border-green-900 dark:bg-green-950/40 px-4 py-3 text-sm text-green-700 dark:text-green-400">
          {runMessage}
        </div>
      )}

      {runError && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-400">
          <strong>Could not start processing:</strong> {runError}
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-400">
          <strong>Could not load emails:</strong> {error}
        </div>
      )}

      {loading && (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {!loading && !error && emails.length > 0 && (
        <>
          <p className="text-xs text-[var(--color-text-muted)] mb-3">
            {emails.length} {emails.length === 1 ? "email" : "emails"} processed
          </p>
          <div className="flex flex-col gap-2">
            {emails.map((email) => (
              <EmailRow key={email.email_id} email={email} />
            ))}
          </div>
        </>
      )}

      {!loading && !error && emails.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center gap-3">
          <Inbox size={40} className="text-[var(--color-text-muted)]" />
          <p className="text-sm text-[var(--color-text-muted)]">No emails processed yet.</p>
        </div>
      )}
    </div>
  );
}
