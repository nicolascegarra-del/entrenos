"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { refreshAccessToken } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

/**
 * Protege las rutas privadas. El access token solo vive en memoria, así que al
 * recargar la página se intenta recuperar con la cookie de refresh.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const accessToken = useAuthStore((s) => s.accessToken);
  const [checking, setChecking] = useState(!accessToken);

  useEffect(() => {
    if (accessToken) return;
    refreshAccessToken().then((ok) => {
      if (ok) setChecking(false);
      else router.replace("/login");
    });
  }, [accessToken, router]);

  if (checking && !accessToken) {
    return (
      <div className="flex min-h-dvh items-center justify-center" role="status">
        <Loader2 className="size-8 animate-spin text-klyp-accent" aria-hidden />
        <span className="sr-only">Cargando…</span>
      </div>
    );
  }
  return <AppShell>{children}</AppShell>;
}
