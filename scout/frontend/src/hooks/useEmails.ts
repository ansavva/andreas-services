import { useCallback, useEffect, useState } from "react";
import type { ProcessedEmail } from "@/types";

const API_BASE = import.meta.env.VITE_API_URL as string;

interface UseEmailsResult {
  emails: ProcessedEmail[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useEmails(): UseEmailsResult {
  const [emails, setEmails] = useState<ProcessedEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchEmails = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/admin/emails`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const data = (await res.json()) as { emails: ProcessedEmail[] };
      setEmails(data.emails ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchEmails();
  }, [fetchEmails]);

  return { emails, loading, error, refetch: fetchEmails };
}
