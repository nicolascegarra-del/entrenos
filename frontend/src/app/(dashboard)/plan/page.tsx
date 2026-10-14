"use client";

import { ChevronLeft, ChevronRight, Clock, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ScoreBadge } from "@/components/plan/status-badge";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useActivitiesInRange, usePlans } from "@/hooks/use-api";
import { formatDistance, formatDuration, sportInfo } from "@/lib/format";
import { addDays, startOfWeek, toIsoDay } from "@/lib/plan";
import { cn } from "@/lib/utils";
import type { ActivitySummary, PlannedSession } from "@/types/api";

const WEEKDAYS = [
  "Lunes",
  "Martes",
  "Miércoles",
  "Jueves",
  "Viernes",
  "Sábado",
  "Domingo",
];

function localIsoDay(iso: string): string {
  return toIsoDay(new Date(iso));
}

function PlannedCard({ plan }: { plan: PlannedSession }) {
  const { icon: Icon } = sportInfo(plan.sport);
  const today = toIsoDay(new Date());
  const pending = plan.activity_id == null && plan.day < today;
  return (
    <Link
      href={`/plan/${plan.id}`}
      className="block rounded-md border border-border bg-card p-2 text-sm shadow-sm transition-colors hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <p className="flex items-start gap-1.5 font-medium">
        <Icon className="mt-0.5 size-4 shrink-0 text-klyp-accent" aria-hidden />
        <span className="line-clamp-2">{plan.title}</span>
      </p>
      <p className="mt-1 text-xs text-muted-foreground tabular-nums">
        {plan.planned_distance_m
          ? `${formatDistance(plan.planned_distance_m)} · `
          : ""}
        ~{formatDuration(plan.planned_duration_s)}
      </p>
      <div className="mt-1.5">
        {plan.compliance_score != null ? (
          <ScoreBadge score={plan.compliance_score} />
        ) : pending ? (
          <span className="text-xs text-muted-foreground">Sin actividad</span>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="size-3" aria-hidden /> Planificada
          </span>
        )}
      </div>
    </Link>
  );
}

function UnplannedCard({ activity }: { activity: ActivitySummary }) {
  const { icon: Icon, label } = sportInfo(activity.sport);
  return (
    <Link
      href={`/actividades/${activity.id}`}
      className="block rounded-md border border-dashed border-border p-2 text-xs text-muted-foreground hover:bg-muted/60"
    >
      <span className="flex items-center gap-1.5">
        <Icon className="size-3.5" aria-hidden /> {label} sin plan
      </span>
      <span className="tabular-nums">
        {formatDistance(activity.distance_m)} ·{" "}
        {formatDuration(activity.duration_s)}
      </span>
    </Link>
  );
}

export default function PlanPage() {
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  const from = toIsoDay(days[0]);
  const to = toIsoDay(days[6]);
  const plans = usePlans(from, to);
  const activities = useActivitiesInRange(from, to);
  const today = toIsoDay(new Date());

  const matched = new Set((plans.data ?? []).map((p) => p.activity_id));
  const unplanned = (activities.data?.items ?? []).filter(
    (a) => !matched.has(a.id),
  );
  const rangeLabel = `${days[0].toLocaleDateString("es-ES", { day: "numeric", month: "short" })} – ${days[6].toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "numeric" })}`;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-heading text-2xl font-bold md:text-3xl">Plan</h1>
        <Button asChild className="min-h-11">
          <Link
            href={`/plan/nueva?dia=${today >= from && today <= to ? today : from}`}
          >
            <Plus aria-hidden /> Nueva sesión
          </Link>
        </Button>
      </div>

      <div className="flex items-center justify-between gap-2 rounded-lg bg-muted/60 p-1">
        <Button
          variant="ghost"
          size="icon"
          className="size-11"
          aria-label="Semana anterior"
          onClick={() => setWeekStart(addDays(weekStart, -7))}
        >
          <ChevronLeft />
        </Button>
        <button
          type="button"
          className="min-h-11 text-sm font-medium"
          onClick={() => setWeekStart(startOfWeek(new Date()))}
          title="Ir a la semana actual"
        >
          {rangeLabel}
        </button>
        <Button
          variant="ghost"
          size="icon"
          className="size-11"
          aria-label="Semana siguiente"
          onClick={() => setWeekStart(addDays(weekStart, 7))}
        >
          <ChevronRight />
        </Button>
      </div>

      {plans.isError ? (
        <ErrorState
          message="No se pudo cargar el plan."
          onRetry={() => plans.refetch()}
        />
      ) : (
        <ol className="grid gap-2 lg:grid-cols-7">
          {days.map((day, i) => {
            const iso = toIsoDay(day);
            const dayPlans = (plans.data ?? []).filter((p) => p.day === iso);
            const dayUnplanned = unplanned.filter(
              (a) => localIsoDay(a.start_time) === iso,
            );
            const empty =
              !plans.isPending && !dayPlans.length && !dayUnplanned.length;
            return (
              <li
                key={iso}
                className={cn(
                  "flex min-h-16 flex-col gap-2 rounded-lg border border-border p-2 lg:min-h-48",
                  iso === today && "border-klyp-accent ring-1 ring-klyp-accent",
                  empty && "max-lg:min-h-0",
                )}
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-foreground">
                    {WEEKDAYS[i]}{" "}
                    <span className="font-normal text-muted-foreground">
                      {day.getDate()}
                    </span>
                  </span>
                  <Link
                    href={`/plan/nueva?dia=${iso}`}
                    className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                    aria-label={`Planificar el ${WEEKDAYS[i].toLowerCase()} ${day.getDate()}`}
                  >
                    <Plus className="size-4" />
                  </Link>
                </div>
                {plans.isPending ? (
                  <Skeleton className="h-14 w-full" />
                ) : (
                  <>
                    {dayPlans.map((p) => (
                      <PlannedCard key={p.id} plan={p} />
                    ))}
                    {dayUnplanned.map((a) => (
                      <UnplannedCard key={a.id} activity={a} />
                    ))}
                    {empty && (
                      <p className="hidden text-xs text-muted-foreground lg:block">
                        Descanso
                      </p>
                    )}
                  </>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
