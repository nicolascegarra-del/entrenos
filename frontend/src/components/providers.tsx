"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState } from "react";

import { Toaster } from "@/components/ui/sonner";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 60_000, retry: 1 } },
      }),
  );
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      <QueryClientProvider client={queryClient}>
        {children}
        {/* Abajo y por encima de la barra de pestañas: arriba quedaban tapados por la barra de estado del móvil. */}
        <Toaster
          richColors
          closeButton
          position="bottom-center"
          duration={6000}
          offset={{ bottom: 24 }}
          mobileOffset={{
            bottom: "calc(5.5rem + env(safe-area-inset-bottom))",
            left: 12,
            right: 12,
          }}
        />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
