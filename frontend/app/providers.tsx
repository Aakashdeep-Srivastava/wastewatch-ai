"use client";

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// App-wide TanStack Query provider. One stable QueryClient per browser session
// (created inside useState so it survives re-renders but is never shared across
// requests on the server). Zustand needs no provider — its stores are module
// singletons imported directly where used.
export default function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000, // treat server reads as fresh for 30s
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
