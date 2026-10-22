"use client";

import { Loader2 } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { useMe } from "@/hooks/use-api";
import { refreshAccessToken } from "@/lib/api";
import { needsOnboarding } from "@/lib/onboarding";
import { useAuthStore } from "@/stores/auth";

/**
 * Protege las rutas privadas. El access token solo vive en memoria, así que al
 * recargar la página se intenta recuperar con la cookie de refresh.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
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
    return <Loading />;
  }
  return (
    <Onboarded pathname={pathname}>
      {pathname === "/bienvenida" ? (
        // La configuración guiada va a pantalla completa, sin menú, para no despistar.
        <main className="min-h-dvh bg-background p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] md:p-8">
          {children}
        </main>
      ) : (
        <AppShell>{children}</AppShell>
      )}
    </Onboarded>
  );
}

function Loading() {
  return (
    <div className="flex min-h-dvh items-center justify-center" role="status">
      <Loader2 className="size-8 animate-spin text-klyp-accent" aria-hidden />
      <span className="sr-only">Cargando…</span>
    </div>
  );
}

/** La primera vez que alguien entra (sin configuración guiada hecha) lo lleva a /bienvenida. */
function Onboarded({
  pathname,
  children,
}: {
  pathname: string;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { data: me } = useMe();
  const redirect = needsOnboarding(me, pathname);
  useEffect(() => {
    if (redirect) router.replace("/bienvenida");
  }, [redirect, router]);
  return redirect ? <Loading /> : children;
}
