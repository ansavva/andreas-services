import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { Toast } from "@ansavva/design-system";

/**
 * The providers a component needs to render at all, for tests.
 *
 * The query client and the toast store. Both are required rather than optional
 * — `useQuery` throws without one, and `useToast` throws without the other by
 * design — so every test that renders anything reading a resource or
 * reporting a write needs them, which is most of them.
 *
 * **A fresh client per call, and no retries.** A client shared across cases
 * would carry one test's answers into the next, which is the shape of a suite
 * that passes in order and fails alone. Retries are off so a case asserting an
 * error state reaches it on the first rejection rather than after three.
 *
 * `gcTime: 0` for the same reason: nothing outlives the test that fetched it.
 *
 * The toast viewport is mounted too, so a test can assert that a write
 * reported itself — the message lands in `document.body`, where `screen` sees
 * it.
 */
export function TestProviders({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false },
    },
  });
  return (
    <QueryClientProvider client={client}>
      <Toast.Provider>
        {children}
        <Toast.Viewport />
      </Toast.Provider>
    </QueryClientProvider>
  );
}
