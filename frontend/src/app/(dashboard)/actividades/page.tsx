"use client";

import {
  ChevronRight,
  FileUp,
  Footprints,
  ListChecks,
  Loader2,
  Search,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useActivities, useDeleteActivities, useSports } from "@/hooks/use-api";
import {
  formatDateTime,
  formatDistance,
  formatDuration,
  formatNumber,
  formatPace,
  formatSpeedKmh,
  sportInfo,
} from "@/lib/format";
import { groupByWeek, weekLabel } from "@/lib/weeks";
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

interface Selection {
  on: boolean;
  ids: Set<number>;
  toggle: (id: number) => void;
}

function ActivityCard({
  activity,
  selection,
}: {
  activity: ActivitySummary;
  selection: Selection;
}) {
  const { icon: Icon, label } = sportInfo(activity.sport);
  const checked = selection.ids.has(activity.id);
  const content = (
    <Card
      className={cn(
        "py-0 shadow-sm transition-colors hover:bg-muted/50",
        checked && "border-klyp-accent bg-klyp-accent/5",
      )}
    >
      <CardContent className="flex items-center gap-3 p-3">
        {selection.on && (
          <input
            type="checkbox"
            className="size-5 shrink-0"
            checked={checked}
            onChange={() => selection.toggle(activity.id)}
            aria-label={`Seleccionar ${activity.name || label}`}
          />
        )}
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
        {!selection.on && (
          <ChevronRight
            className="size-5 shrink-0 text-muted-foreground"
            aria-hidden
          />
        )}
      </CardContent>
    </Card>
  );
  return selection.on ? (
    <div
      role="presentation"
      className="block cursor-pointer rounded-lg"
      onClick={(e) => {
        if ((e.target as HTMLElement).tagName !== "INPUT")
          selection.toggle(activity.id);
      }}
    >
      {content}
    </div>
  ) : (
    <Link
      href={`/actividades/${activity.id}`}
      className="block rounded-lg focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      {content}
    </Link>
  );
}

function ActivityTable({
  activities,
  selection,
}: {
  activities: ActivitySummary[];
  selection: Selection;
}) {
  return (
    <Card className="py-0 shadow-sm">
      <Table>
        <TableHeader>
          <TableRow>
            {selection.on && (
              <TableHead className="w-10">
                <span className="sr-only">Seleccionar</span>
              </TableHead>
            )}
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
              <TableRow
                key={a.id}
                data-state={selection.ids.has(a.id) ? "selected" : undefined}
              >
                {selection.on && (
                  <TableCell>
                    <input
                      type="checkbox"
                      className="size-4"
                      checked={selection.ids.has(a.id)}
                      onChange={() => selection.toggle(a.id)}
                      aria-label={`Seleccionar ${a.name || label}`}
                    />
                  </TableCell>
                )}
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

/** Lista del móvil agrupada por semanas, con los km y entrenos de cada una. */
function WeekList({
  activities,
  selection,
}: {
  activities: ActivitySummary[];
  selection: Selection;
}) {
  return (
    <div className="space-y-4">
      {groupByWeek(activities, (a) => a.start_time).map((g) => {
        const km = g.items.reduce((sum, a) => sum + (a.distance_m ?? 0), 0);
        return (
          <section
            key={g.week}
            aria-label={weekLabel(g.week)}
            className="space-y-2"
          >
            <h2 className="flex items-baseline justify-between text-sm font-semibold">
              {weekLabel(g.week)}
              <span className="text-xs font-normal text-muted-foreground tabular-nums">
                {formatDistance(km)} · {g.items.length}{" "}
                {g.items.length === 1 ? "entreno" : "entrenos"}
              </span>
            </h2>
            {g.items.map((a) => (
              <ActivityCard key={a.id} activity={a} selection={selection} />
            ))}
          </section>
        );
      })}
    </div>
  );
}

/** Entrenos → Actividades: búsqueda, filtro por deporte y lista por semanas. */
export default function ActividadesPage() {
  const [sport, setSport] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQuery(text), 300);
    return () => clearTimeout(t);
  }, [text]);
  const {
    data,
    isPending,
    isError,
    refetch,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
  } = useActivities(sport, query);
  const activities = data?.pages.flatMap((p) => p.items) ?? [];
  const remove = useDeleteActivities();
  const [selecting, setSelecting] = useState(false);
  const [ids, setIds] = useState<Set<number>>(new Set());
  const selection: Selection = {
    on: selecting,
    ids,
    toggle: (id) =>
      setIds((prev) => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      }),
  };
  const stopSelecting = () => {
    setSelecting(false);
    setIds(new Set());
  };
  const deleteSelected = () => {
    const n = ids.size;
    if (
      !n ||
      !window.confirm(
        `¿Borrar ${n} ${n === 1 ? "actividad" : "actividades"}? Se quitan sus datos y no volverán a traerse al sincronizar. No se puede deshacer.`,
      )
    )
      return;
    remove.mutate([...ids], {
      onSuccess: (r) => {
        toast.success(
          `${r.deleted} ${r.deleted === 1 ? "actividad borrada" : "actividades borradas"}.`,
        );
        stopSelecting();
      },
      onError: () => toast.error("No se pudieron borrar."),
    });
  };

  return (
    <section className="space-y-4">
      <PageHeader
        title="Actividades"
        hideTitleOnMobile
        actions={
          <>
            {activities.length > 0 && (
              <Button
                data-tour="select-activities"
                variant={selecting ? "secondary" : "ghost"}
                size="sm"
                className="min-h-11 md:min-h-8"
                onClick={() =>
                  selecting ? stopSelecting() : setSelecting(true)
                }
              >
                {selecting ? <X aria-hidden /> : <ListChecks aria-hidden />}
                {selecting ? "Cancelar" : "Seleccionar"}
              </Button>
            )}
            <Button
              asChild
              data-tour="import"
              variant="outline"
              size="sm"
              className="min-h-11 md:min-h-8"
            >
              <Link
                href="/ajustes/conexiones"
                title="Importar entrenos de tu reloj (ficheros FIT, GPX o TCX)"
              >
                <FileUp aria-hidden /> Importar
              </Link>
            </Button>
          </>
        }
      />
      <div className="relative" data-tour="activity-search">
        <Search
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          type="search"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Buscar por nombre"
          aria-label="Buscar actividades por nombre"
          className="h-11 pl-9 md:h-9"
        />
      </div>
      <div data-tour="sport-filter">
        <SportFilter value={sport} onChange={setSport} />
      </div>

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
      ) : activities.length === 0 && (query || sport) ? (
        <EmptyState icon={Search} title="Sin resultados">
          <p className="max-w-sm text-sm text-muted-foreground">
            No hay actividades que coincidan. Prueba con otro nombre o deporte.
          </p>
        </EmptyState>
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
          <div className="lg:hidden">
            <WeekList activities={activities} selection={selection} />
          </div>
          <div className="hidden lg:block">
            <ActivityTable activities={activities} selection={selection} />
          </div>
          {selecting && (
            <div className="sticky bottom-20 z-20 flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3 shadow-md lg:bottom-4">
              <span className="text-sm font-medium tabular-nums">
                {ids.size} {ids.size === 1 ? "seleccionada" : "seleccionadas"}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="min-h-11 md:min-h-8"
                onClick={() =>
                  setIds(
                    ids.size === activities.length
                      ? new Set()
                      : new Set(activities.map((a) => a.id)),
                  )
                }
              >
                {ids.size === activities.length ? "Ninguna" : "Todas"}
              </Button>
              <Button
                variant="destructive"
                size="sm"
                className="ml-auto min-h-11 md:min-h-8"
                disabled={!ids.size || remove.isPending}
                onClick={deleteSelected}
              >
                {remove.isPending ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <Trash2 aria-hidden />
                )}
                Borrar
              </Button>
            </div>
          )}
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
