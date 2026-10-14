"use client";

import { ChevronRight, Footprints, Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useActivities, useSports } from "@/hooks/use-api";
import {
  formatDateTime,
  formatDistance,
  formatDuration,
  formatNumber,
  formatPace,
  formatSpeedKmh,
  sportInfo,
} from "@/lib/format";
import type { ActivitySummary } from "@/types/api";

function speedLabel(a: ActivitySummary): string {
  if (!a.distance_m || !a.duration_s) return "—";
  const speed = a.metrics.avg_speed ?? a.distance_m / a.duration_s;
  return sportInfo(a.sport).pace ? formatPace(speed) : formatSpeedKmh(speed);
}

function SportFilter({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (s: string | null) => void;
}) {
  const { data: sports } = useSports();
  if (!sports || sports.length < 2) return null;
  const options: (string | null)[] = [null, ...sports];
  return (
    <div
      className="flex gap-2 overflow-x-auto pb-1"
      role="group"
      aria-label="Filtrar por deporte"
    >
      {options.map((sport) => (
        <Button
          key={sport ?? "all"}
          size="sm"
          variant={value === sport ? "default" : "outline"}
          className="min-h-11 shrink-0 md:min-h-9"
          aria-pressed={value === sport}
          onClick={() => onChange(sport)}
        >
          {sport ? sportInfo(sport).label : "Todas"}
        </Button>
      ))}
    </div>
  );
}

function ActivityCard({ activity }: { activity: ActivitySummary }) {
  const { icon: Icon, label } = sportInfo(activity.sport);
  return (
    <Link
      href={`/actividades/${activity.id}`}
      className="block rounded-lg focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <Card className="py-0 shadow-sm transition-colors hover:bg-muted/50">
        <CardContent className="flex items-center gap-3 p-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted text-primary dark:text-foreground">
            <Icon className="size-5" aria-label={label} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{activity.name || label}</p>
            <p className="text-xs text-muted-foreground">
              {formatDateTime(activity.start_time)}
            </p>
            <p className="mt-1 text-sm tabular-nums">
              {formatDistance(activity.distance_m)} ·{" "}
              {formatDuration(activity.duration_s)} · {speedLabel(activity)}
            </p>
          </div>
          <ChevronRight
            className="size-5 shrink-0 text-muted-foreground"
            aria-hidden
          />
        </CardContent>
      </Card>
    </Link>
  );
}

function ActivityTable({ activities }: { activities: ActivitySummary[] }) {
  return (
    <Card className="py-0 shadow-sm">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Actividad</TableHead>
            <TableHead>Fecha</TableHead>
            <TableHead className="text-right">Distancia</TableHead>
            <TableHead className="text-right">Duración</TableHead>
            <TableHead className="text-right">Ritmo / vel.</TableHead>
            <TableHead className="text-right">FC media</TableHead>
            <TableHead className="text-right">Desnivel +</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {activities.map((a) => {
            const { icon: Icon, label } = sportInfo(a.sport);
            return (
              <TableRow key={a.id}>
                <TableCell>
                  <Link
                    href={`/actividades/${a.id}`}
                    className="flex items-center gap-2 font-medium hover:underline"
                  >
                    <Icon
                      className="size-4 text-klyp-accent"
                      aria-label={label}
                    />
                    {a.name || label}
                  </Link>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {formatDateTime(a.start_time)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatDistance(a.distance_m)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatDuration(a.duration_s)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {speedLabel(a)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {a.avg_hr ? `${formatNumber(a.avg_hr)} ppm` : "—"}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {a.elevation_gain_m != null
                    ? `${formatNumber(a.elevation_gain_m)} m`
                    : "—"}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Card>
  );
}

export default function ActividadesPage() {
  const [sport, setSport] = useState<string | null>(null);
  const {
    data,
    isPending,
    isError,
    refetch,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
  } = useActivities(sport);
  const activities = data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <section className="space-y-4">
      <h1 className="font-heading text-2xl font-bold md:text-3xl">
        Actividades
      </h1>
      <SportFilter value={sport} onChange={setSport} />

      {isPending ? (
        <div
          className="space-y-2"
          role="status"
          aria-label="Cargando actividades"
        >
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-20 w-full lg:h-12" />
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          message="No se pudieron cargar las actividades."
          onRetry={() => refetch()}
        />
      ) : activities.length === 0 ? (
        <EmptyState icon={Footprints} title="Aún no hay actividades">
          <p className="max-w-sm text-sm text-muted-foreground">
            Conecta Garmin y sincroniza desde{" "}
            <Link
              href="/ajustes"
              className="font-medium text-klyp-accent underline"
            >
              Ajustes
            </Link>
            .
          </p>
        </EmptyState>
      ) : (
        <>
          <div className="space-y-2 lg:hidden">
            {activities.map((a) => (
              <ActivityCard key={a.id} activity={a} />
            ))}
          </div>
          <div className="hidden lg:block">
            <ActivityTable activities={activities} />
          </div>
          {hasNextPage && (
            <div className="flex justify-center">
              <Button
                variant="outline"
                className="min-h-11"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
              >
                {isFetchingNextPage && (
                  <Loader2 className="animate-spin" aria-hidden />
                )}
                Cargar más
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
