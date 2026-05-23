import { useState } from "react";
import { ChevronDown, ChevronRight, Inbox, Mail } from "lucide-react";
import { useEmails } from "@/hooks/useEmails";
import { Header } from "@/components/Header";
import { SkeletonCard } from "@/components/SkeletonCard";
import type { ProcessedEmail } from "@/types";

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

interface EmailRowProps {
  email: ProcessedEmail;
}

function EmailRow({ email }: EmailRowProps) {
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

        <span className="flex-shrink-0 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-[var(--color-badge-bg)] text-[var(--color-badge-text)]">
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

export function AdminPage() {
  const { emails, loading, error, refetch } = useEmails();

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <Header onRefresh={refetch} loading={loading} />

      <main className="max-w-4xl mx-auto px-4 py-8">
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
            Processed Emails
          </h2>
          <p className="text-sm text-[var(--color-text-muted)]">
            Emails Scout has fetched and extracted events from.
          </p>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-400">
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
          <div className="flex flex-col items-center justify-center py-24 text-center gap-4">
            <Inbox size={48} className="text-[var(--color-text-muted)]" />
            <h2 className="text-lg font-medium text-[var(--color-text-secondary)]">
              No emails processed yet
            </h2>
            <p className="text-sm text-[var(--color-text-muted)] max-w-sm">
              The email processor runs every Monday. Once it runs, processed emails will appear here.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
