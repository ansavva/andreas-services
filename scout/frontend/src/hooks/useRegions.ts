import { useCallback, useEffect, useState } from "react";
import type { Region } from "@/types";

const API_BASE = import.meta.env.VITE_API_URL as string;

interface UseRegionsResult {
  regions: Region[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useRegions(): UseRegionsResult {
  const [regions, setRegions] = useState<Region[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRegions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/regions`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const data = (await res.json()) as { regions: Region[] };
      setRegions(data.regions ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchRegions();
  }, [fetchRegions]);

  return { regions, loading, error, refetch: fetchRegions };
}
