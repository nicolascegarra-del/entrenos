"use client";

import { useParams } from "next/navigation";

import { PageHeader } from "@/components/layout/page-header";
import { RouteActions } from "@/components/routes/route-actions";
import { RouteEditor } from "@/components/routes/route-editor";
import { ErrorState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { usePlannedRoute } from "@/hooks/use-api";

/** Una ruta guardada: se edita en el mapa y se exporta, se usa en el plan o se le pregunta al entrenador. */
export default function RutaPage() {
  const id = Number(useParams<{ id: string }>().id);
  const { data, isPending, isError, refetch } = usePlannedRoute(
    Number.isFinite(id) ? id : null,
  );
  if (isPending) return <Skeleton className="h-[60dvh] w-full" />;
  if (isError || !data)
    return (
      <ErrorState
        message="No se pudo cargar la ruta."
        onRetry={() => refetch()}
      />
    );
  return (
    <section className="space-y-3">
      <PageHeader
        title={data.name}
        back={{ href: "/plan/rutas", label: "Rutas" }}
      />
      <RouteEditor key={data.id} initial={data} />
      <RouteActions route={data} />
    </section>
  );
}
