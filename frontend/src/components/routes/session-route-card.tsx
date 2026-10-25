"use client";

import { MapPinned, X } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { toast } from "sonner";

import { ElevationProfile } from "@/components/routes/elevation-profile";
import { RouteStatsGrid } from "@/components/routes/route-editor";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePlannedRoute, useSetSessionRoute } from "@/hooks/use-api";

const RouteMap = dynamic(() => import("@/components/activity/route-map"), {
  ssr: false,
  loading: () => <Skeleton className="h-64 w-full md:h-80" />,
});

/** La ruta del mapa de una sesión del plan: traza, desnivel y perfil, con enlace para editarla o quitarla. */
export function SessionRouteCard({
  planId,
  routeId,
}: {
  planId: number;
  routeId: number;
}) {
  const { data: route } = usePlannedRoute(routeId);
  const setRoute = useSetSessionRoute();
  return (
    <Card className="shadow-sm">
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="flex min-w-0 items-center gap-2 font-heading text-lg">
          <MapPinned className="size-5 shrink-0 text-klyp-accent" aria-hidden />
          <span className="truncate">{route?.name ?? "Ruta"}</span>
        </CardTitle>
        <Button
          variant="ghost"
          size="sm"
          className="min-h-11 text-muted-foreground md:min-h-8"
          disabled={setRoute.isPending}
          onClick={() =>
            setRoute.mutate(
              { planId, routeId: null },
              { onSuccess: () => toast.success("Ruta quitada de la sesión.") },
            )
          }
        >
          <X aria-hidden /> Quitar
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {!route ? (
          <Skeleton className="h-64" />
        ) : (
          <>
            <RouteMap
              points={route.geometry.map((g) => [
                g[0] as number,
                g[1] as number,
              ])}
            />
            <RouteStatsGrid plan={route} />
            <ElevationProfile profile={route.profile} />
            <Button asChild variant="outline" className="min-h-11 md:min-h-9">
              <Link href={`/plan/rutas/${route.id}`}>
                Ver o editar la ruta · Exportar GPX
              </Link>
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
