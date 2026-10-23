"use client";

import type { LatLngTuple } from "leaflet";
import { Ellipsis, Watch } from "lucide-react";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { AskAi } from "@/components/activity/ask-ai";
import { FeedbackCard } from "@/components/activity/feedback-card";
import { GearSelect } from "@/components/activity/gear-select";
import { LapsTable } from "@/components/activity/laps-table";
import { RaceToggle } from "@/components/activity/race-toggle";
import { ActivityAnalysisCards } from "@/components/activity/analysis-cards";
import { DeleteActivity } from "@/components/activity/delete-activity";
import { ExportActivity } from "@/components/activity/export-activity";
import { ReviewCard } from "@/components/activity/review-card";
import { ActivityTestCard, MarkTest } from "@/components/tests/activity-test";
import { LactateForm } from "@/components/tests/test-forms";
import { RouteCard } from "@/components/activity/route-card";
import {
  StreamCharts,
  chartChannels,
} from "@/components/activity/stream-charts";
import { PageHeader } from "@/components/layout/page-header";
import { ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { useActivity, useCatalog, useStreams } from "@/hooks/use-api";
import { ApiError } from "@/lib/api";
import { usesShoes } from "@/lib/gear";
import {
  formatDateTime,
  formatDistance,
  formatDuration,
  formatNumber,
  formatPace,
  formatSpeedKmh,
  sportInfo,
} from "@/lib/format";
import type { ActivityDetail, MetricDefinition } from "@/types/api";

const RouteMap = dynamic(() => import("@/components/activity/route-map"), {
  ssr: false,
  loading: () => <Skeleton className="h-64 w-full md:h-80" />,
});

/** Valor de una métrica del catálogo: tiempos (unidad "s") como m:ss; enteros sin decimales. */
function metricValue(m: MetricDefinition, value: number): string {
  if (m.unit === "s") return formatDuration(value);
  const decimals = Number.isInteger(value) || m.unit ? 0 : 1;
  return `${formatNumber(value, decimals)}${m.unit ? ` ${m.unit}` : ""}`;
}

// Métricas que ya salen en las tarjetas principales.
const SHOWN_ELSEWHERE = new Set(["avg_speed"]);

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg bg-muted/60 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-lg font-semibold tabular-nums md:text-xl">
        {value}
      </p>
      {sub && (
        <p className="text-xs text-muted-foreground tabular-nums">{sub}</p>
      )}
    </div>
  );
}

/**
 * Tarjetas de métricas: las fijas (distancia, tiempo…) más las que el reloj haya
 * aportado y estén en el catálogo, así un reloj con más métricas las muestra solo.
 */
function StatsGrid({
  activity,
  catalog,
}: {
  activity: ActivityDetail;
  catalog: MetricDefinition[];
}) {
  const { pace } = sportInfo(activity.sport);
  const speed =
    activity.metrics.avg_speed ??
    (activity.distance_m ? activity.distance_m / activity.duration_s : null);
  const extra = catalog.filter(
    (m) =>
      m.scope === "activity" &&
      !SHOWN_ELSEWHERE.has(m.key) &&
      activity.metrics[m.key] != null,
  );
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {activity.distance_m ? (
          <Stat label="Distancia" value={formatDistance(activity.distance_m)} />
        ) : null}
        <Stat
          label="Tiempo en movimiento"
          value={formatDuration(
            activity.moving_duration_s ?? activity.duration_s,
          )}
          sub={`total ${formatDuration(activity.duration_s)}`}
        />
        {speed ? (
          <Stat
            label={pace ? "Ritmo medio" : "Velocidad media"}
            value={pace ? formatPace(speed) : formatSpeedKmh(speed)}
          />
        ) : null}
        {activity.avg_hr ? (
          <Stat
            label="FC media"
            value={`${formatNumber(activity.avg_hr)} ppm`}
            sub={`máx. ${formatNumber(activity.max_hr)}`}
          />
        ) : null}
        {activity.elevation_gain_m != null ? (
          <Stat
            label="Desnivel +"
            value={`${formatNumber(activity.elevation_gain_m)} m`}
          />
        ) : null}
      </div>
      {(activity.calories || extra.length > 0) && (
        <details className="group">
          <summary className="min-h-11 cursor-pointer content-center text-sm text-klyp-accent">
            <span className="group-open:hidden">
              Todas las métricas ({extra.length + (activity.calories ? 1 : 0)})
            </span>
            <span className="hidden group-open:inline">Ocultar métricas</span>
          </summary>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            {activity.calories ? (
              <Stat
                label="Calorías"
                value={`${formatNumber(activity.calories)} kcal`}
              />
            ) : null}
            {extra.map((m) => (
              <Stat
                key={m.key}
                label={m.label}
                value={metricValue(m, activity.metrics[m.key])}
              />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

export default function ActivityDetailPage() {
  const id = Number(useParams<{ id: string }>().id);
  const {
    data: activity,
    isPending,
    isError,
    error,
    refetch,
  } = useActivity(id);
  const { data: catalog = [] } = useCatalog();
  const [lactateOpen, setLactateOpen] = useState(false);
  const channels = activity
    ? [...chartChannels(activity.channels), "lat", "lon"]
    : [];
  const { data: streams, isPending: streamsPending } = useStreams(
    id,
    channels,
    !!activity,
  );

  const route = useMemo<LatLngTuple[]>(() => {
    const lat = streams?.channels.lat ?? [];
    const lon = streams?.channels.lon ?? [];
    return lat.flatMap((la, i) =>
      la != null && lon[i] != null
        ? [[la, lon[i] as number] as LatLngTuple]
        : [],
    );
  }, [streams]);

  if (isPending) {
    return (
      <div className="space-y-4" role="status" aria-label="Cargando actividad">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (isError) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <ErrorState
        message={
          notFound
            ? "Esta actividad no existe."
            : "No se pudo cargar la actividad."
        }
        onRetry={notFound ? undefined : () => refetch()}
      />
    );
  }

  const { label, icon: Icon, pace } = sportInfo(activity.sport);
  return (
    <article className="space-y-4 md:space-y-6">
      <PageHeader
        back={{ href: "/actividades", label: "Actividades" }}
        title={
          <span className="inline-flex items-center gap-2">
            <Icon className="size-6 shrink-0 text-klyp-accent" aria-hidden />
            {activity.name || label}
          </span>
        }
        subtitle={
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {formatDateTime(activity.start_time)} · {label}
            {activity.device && (
              <span className="inline-flex items-center gap-1">
                · <Watch className="size-3" aria-hidden />{" "}
                {activity.device.name}
              </span>
            )}
            {activity.is_race && (
              <Badge variant="secondary">Carrera a tope</Badge>
            )}
          </span>
        }
        actions={
          <>
            <AskAi activity={activity} />
            {
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    size="icon"
                    className="size-11 md:size-8"
                    aria-label="Más opciones de la actividad"
                  >
                    <Ellipsis aria-hidden />
                  </Button>
                </PopoverTrigger>
                <PopoverContent align="end" className="w-72 space-y-3">
                  {usesShoes(activity.sport) && (
                    <>
                      <div className="space-y-1">
                        <p className="text-xs font-medium text-muted-foreground">
                          Zapatillas
                        </p>
                        <GearSelect activity={activity} />
                      </div>
                      <div className="space-y-1">
                        <p className="text-xs font-medium text-muted-foreground">
                          ¿Fue una carrera a tope? Solo esas cuentan para tu
                          nivel.
                        </p>
                        <RaceToggle activity={activity} />
                      </div>
                    </>
                  )}
                  <ExportActivity activityId={activity.id} />
                  <div className="border-t pt-2">
                    <DeleteActivity activityId={activity.id} />
                  </div>
                  <MarkTest
                    activity={activity}
                    onLactate={
                      activity.laps.length >= 4
                        ? () => setLactateOpen(true)
                        : undefined
                    }
                  />
                </PopoverContent>
              </Popover>
            }
          </>
        }
      />

      <StatsGrid activity={activity} catalog={catalog} />

      <ActivityTestCard activityId={activity.id} />

      {lactateOpen && (
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="font-heading text-lg">
              Test de lactato con las vueltas
            </CardTitle>
          </CardHeader>
          <CardContent>
            <LactateForm
              activity={{
                id: activity.id,
                sport: activity.sport,
                date: activity.start_time.slice(0, 10),
                laps: activity.laps,
              }}
              onDone={() => setLactateOpen(false)}
            />
          </CardContent>
        </Card>
      )}

      <ReviewCard activity={activity} />

      <div className="grid gap-4 lg:grid-cols-2 md:gap-6">
        {(streamsPending || route.length > 1) && (
          <Card className="shadow-sm lg:order-2">
            <CardHeader>
              <CardTitle className="font-heading text-lg">Recorrido</CardTitle>
            </CardHeader>
            <CardContent>
              {streamsPending ? (
                <Skeleton className="h-64 w-full md:h-80" />
              ) : (
                <RouteMap points={route} />
              )}
            </CardContent>
          </Card>
        )}
        <Card className="shadow-sm lg:order-1">
          <CardHeader>
            <CardTitle className="font-heading text-lg">Gráficas</CardTitle>
          </CardHeader>
          <CardContent>
            {streamsPending ? (
              <Skeleton className="h-72 w-full" />
            ) : streams && streams.points > 0 ? (
              <StreamCharts streams={streams} pace={pace} />
            ) : (
              <p className="text-sm text-muted-foreground">
                Esta actividad no tiene datos segundo a segundo.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <ActivityAnalysisCards activityId={activity.id} />

      <LapsTable laps={activity.laps} pace={pace} />

      <FeedbackCard activityId={activity.id} />

      {route.length > 1 && <RouteCard activityId={activity.id} />}
    </article>
  );
}
