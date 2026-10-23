"use client";

import { ChevronRight, Route, Trophy } from "lucide-react";
import Link from "next/link";

import { EmptyState, ErrorState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useRoutes } from "@/hooks/use-api";
import { paceText } from "@/lib/compare";
import { formatDate, formatDistance } from "@/lib/format";

/** Recorridos que se repiten, detectados por su trazado GPS. */
export default function RecorridosPage() {
  const { data, isPending, isError, refetch } = useRoutes();
  return (
    <section className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="font-heading text-2xl font-bold max-lg:sr-only md:text-3xl">
          Recorridos
        </h1>
        <p className="text-sm text-muted-foreground">
          Los caminos que repites, detectados solos por su trazado GPS. Compara
          cada intento con tu mejor marca.
        </p>
      </div>
      {isPending ? (
        <Skeleton className="h-64" />
      ) : isError ? (
        <ErrorState
          message="No se pudieron cargar tus recorridos."
          onRetry={() => refetch()}
        />
      ) : !data.length ? (
        <EmptyState icon={Route} title="Aún no hay recorridos repetidos">
          <p className="max-w-sm text-sm text-muted-foreground">
            Cuando hagas el mismo camino al menos dos veces (con GPS), aparecerá
            aquí.
          </p>
        </EmptyState>
      ) : (
        <ul className="space-y-2">
          {data.map((r) => (
            <li key={r.id}>
              <Link
                href={`/recorridos/${r.id}`}
                className="flex min-h-11 items-center gap-3 rounded-lg border p-3 hover:bg-muted/60"
              >
                <Route
                  className="size-5 shrink-0 text-klyp-accent"
                  aria-hidden
                />
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">{r.name}</span>
                  <span className="block text-xs text-muted-foreground">
                    {r.count} veces · {formatDistance(r.distance_m)} · último{" "}
                    {formatDate(`${r.last.day}T12:00:00`)}
                  </span>
                  {r.best && (
                    <span className="mt-0.5 flex items-center gap-1 text-xs tabular-nums">
                      <Trophy className="size-3 text-klyp-accent" aria-hidden />
                      Mejor: {paceText(r.best.pace_s_km)} /km el{" "}
                      {formatDate(`${r.best.day}T12:00:00`)}
                    </span>
                  )}
                </span>
                <ChevronRight
                  className="size-4 shrink-0 text-muted-foreground"
                  aria-hidden
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
