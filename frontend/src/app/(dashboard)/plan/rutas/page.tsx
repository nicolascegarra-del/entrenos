"use client";

import { MapPinned, Plus } from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/layout/page-header";
import { RouteThumb } from "@/components/routes/route-thumb";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { usePlannedRoutes } from "@/hooks/use-api";
import { formatDate, formatDuration } from "@/lib/format";
import { ROUTE_MODES, routeStats } from "@/lib/route-edit";

/** Plan → Rutas: las rutas dibujadas en el mapa. */
export default function RutasPage() {
  const { data, isPending, isError, refetch } = usePlannedRoutes();
  return (
    <section className="space-y-4">
      <PageHeader
        title="Rutas"
        hideTitleOnMobile
        subtitle="Dibuja tu ruta en el mapa y mira sus kilómetros, desnivel y perfil antes de salir."
        actions={
          <Button asChild className="min-h-11 md:min-h-9" data-tour="new-route">
            <Link href="/plan/rutas/nueva">
              <Plus aria-hidden /> Nueva ruta
            </Link>
          </Button>
        }
      />
      {isPending ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          message="No se pudieron cargar tus rutas."
          onRetry={() => refetch()}
        />
      ) : !data.items.length ? (
        <EmptyState icon={MapPinned} title="Aún no tienes rutas">
          <p className="max-w-sm text-sm text-muted-foreground">
            Marca el inicio, los puntos de paso y el final: la ruta va por
            calles o senderos y te dice el desnivel. Luego la mandas al reloj en
            GPX.
          </p>
          <Button asChild className="mt-2 min-h-11">
            <Link href="/plan/rutas/nueva">
              <Plus aria-hidden /> Crear mi primera ruta
            </Link>
          </Button>
        </EmptyState>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.items.map((r) => (
            <li key={r.id}>
              <Link
                href={`/plan/rutas/${r.id}`}
                className="flex min-h-11 gap-3 rounded-lg border bg-card p-3 shadow-sm hover:bg-muted/60"
              >
                <RouteThumb
                  preview={r.preview}
                  className="size-20 shrink-0 rounded-md bg-muted/60"
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{r.name}</span>
                  <span className="block text-sm text-muted-foreground tabular-nums">
                    {routeStats(r.distance_m, r.ascent_m, r.descent_m)}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {ROUTE_MODES.find((m) => m.key === r.mode)?.label ?? r.mode}
                    {r.estimated_s
                      ? ` · ~${formatDuration(r.estimated_s)}`
                      : ""}{" "}
                    · {formatDate(r.created_at)}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
