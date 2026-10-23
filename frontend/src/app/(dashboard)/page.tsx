"use client";

import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  ChevronRight,
  Flame,
  Clock,
  Footprints,
  Sparkles,
} from "lucide-react";
import Link from "next/link";

import { InfoTerm } from "@/components/glossary/info-term";
import { ScoreBadge } from "@/components/plan/status-badge";
import { INSIGHT_STATUS } from "@/components/progress/insight";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { TodayCard } from "@/components/summary/today-card";
import {
  useAchievements,
  useGoals,
  useInjuryRisk,
  useSummary,
} from "@/hooks/use-api";
import {
  formatDateTime,
  formatDistance,
  formatDuration,
  formatNumber,
  sportInfo,
} from "@/lib/format";
import type { GlossaryKey } from "@/lib/glossary";
import { toIsoDay } from "@/lib/plan";
import { cn } from "@/lib/utils";

function Kpi({
  label,
  term,
  value,
  sub,
  delta,
}: {
  label: string;
  term?: GlossaryKey;
  value: string;
  sub?: string;
  /** Cambio respecto a la semana anterior (en %). */
  delta?: number | null;
}) {
  return (
    <div className="rounded-lg bg-muted/60 p-3">
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        {label}
        {term && <InfoTerm term={term} className="size-3.5" />}
      </p>
      <p className="mt-0.5 text-xl font-semibold tabular-nums md:text-2xl">
        {value}
      </p>
      {delta != null && Number.isFinite(delta) ? (
        <p className="flex items-center gap-0.5 text-xs text-muted-foreground tabular-nums">
          {delta >= 0 ? (
            <ArrowUpRight className="size-3.5" aria-hidden />
          ) : (
            <ArrowDownRight className="size-3.5" aria-hidden />
          )}
          {delta >= 0 ? "+" : ""}
          {formatNumber(delta)} % vs semana pasada
        </p>
      ) : (
        sub && <p className="text-xs text-muted-foreground">{sub}</p>
      )}
    </div>
  );
}

const pct = (now: number, before: number) =>
  before > 0 ? ((now - before) / before) * 100 : null;

/** Aviso de riesgo de lesión en el Resumen: solo aparece si hay algo que vigilar. */
function InjuryBanner() {
  const { data } = useInjuryRisk();
  if (!data || data.status === "good") return null;
  const st = INSIGHT_STATUS[data.status];
  const worst = data.checks.filter((c) => c.status === data.status);
  return (
    <Link
      href="/progresion/salud#lesiones"
      className={cn(
        "flex min-h-11 items-start gap-2 rounded-lg border p-3 text-sm hover:opacity-90",
        st.className,
      )}
    >
      <st.icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span className="min-w-0 flex-1">
        <span className="font-medium">
          <span className="sr-only">{st.label}: </span>
          {worst.map((c) => c.title).join(" · ")}
        </span>
        <span className="block">{worst[0]?.message}</span>
      </span>
      <ChevronRight className="mt-0.5 size-4 shrink-0" aria-hidden />
    </Link>
  );
}

/** Racha semanal y reto de km del mes, con enlace a Logros. */
function StreakStrip() {
  const { data } = useAchievements();
  if (!data) return null;
  const km = data.challenges.find((c) => c.key === "km");
  return (
    <Link
      href="/logros"
      className="flex min-h-11 flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border p-3 text-sm hover:bg-muted/60"
    >
      <span className="flex items-center gap-1.5 font-medium">
        <Flame className="size-4 text-klyp-accent" aria-hidden />
        Racha: {data.streak.current}{" "}
        {data.streak.current === 1 ? "semana" : "semanas"}
      </span>
      <span className="text-muted-foreground tabular-nums">
        Esta semana {data.streak.this_week}/{data.streak.target} entrenos
      </span>
      {km && (
        <span className="text-muted-foreground tabular-nums">
          {km.title}: {formatNumber(km.current, 1)}/{formatNumber(km.target)} km
        </span>
      )}
      <ChevronRight className="ml-auto size-4 shrink-0" aria-hidden />
    </Link>
  );
}

export default function ResumenPage() {
  const { data, isPending, isError, refetch } = useSummary();
  const { data: goals } = useGoals();
  const today = toIsoDay(new Date());

  if (isPending) {
    return (
      <div className="space-y-4" role="status" aria-label="Cargando resumen">
        <Skeleton className="h-10 w-1/3" />
        <Skeleton className="h-64 md:h-40" />
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      </div>
    );
  }
  if (isError)
    return (
      <ErrorState
        message="No se pudo cargar el resumen."
        onRetry={() => refetch()}
      />
    );

  if (!data.recent.length && !data.planned_this_week.length) {
    return (
      <section className="space-y-4">
        <h1 className="font-heading text-2xl font-bold md:text-3xl">Resumen</h1>
        <EmptyState icon={Footprints} title="Empieza conectando Garmin">
          <p className="max-w-sm text-sm text-muted-foreground">
            Sincroniza tus actividades desde{" "}
            <Link
              href="/ajustes"
              className="font-medium text-klyp-accent underline"
            >
              Ajustes
            </Link>{" "}
            o planifica tu primera sesión en{" "}
            <Link
              href="/plan"
              className="font-medium text-klyp-accent underline"
            >
              Plan
            </Link>
            .
          </p>
        </EmptyState>
      </section>
    );
  }

  const { this_week: now, last_week: before, fitness } = data;
  return (
    <section className="space-y-4 md:space-y-6">
      <div className="flex items-center justify-between gap-2">
        <h1 className="font-heading text-2xl font-bold md:text-3xl">Resumen</h1>
        <Button
          asChild
          variant="outline"
          size="sm"
          className="min-h-11 md:min-h-8"
        >
          <Link href="/asistente">
            <Sparkles aria-hidden /> Pregúntale a la IA
          </Link>
        </Button>
      </div>

      <TodayCard summary={data} goals={goals} today={today} />
      <InjuryBanner />
      <StreakStrip />

      <h2 className="font-heading text-lg font-semibold">Esta semana</h2>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Kpi
          label="Distancia"
          value={formatDistance(now.distance_m)}
          delta={pct(now.distance_m, before.distance_m)}
        />
        <Kpi
          label="Tiempo"
          value={formatDuration(now.duration_s)}
          delta={pct(now.duration_s, before.duration_s)}
        />
        <Kpi
          label="Actividades"
          value={String(now.count)}
          sub={`${before.count} la semana pasada`}
        />
        <Kpi
          label="Carga"
          term="load"
          value={formatNumber(now.load)}
          delta={pct(now.load, before.load)}
        />
        <Kpi
          label="Frescura"
          term="tsb"
          value={fitness ? formatNumber(fitness.tsb) : "—"}
          sub={data.form_label ?? undefined}
        />
        <Kpi
          label="Forma física"
          term="ctl"
          value={fitness ? formatNumber(fitness.ctl) : "—"}
          sub="media de 6 semanas"
        />
        <Kpi
          label="VO2max"
          term="vo2max"
          value={data.vo2max ? formatNumber(data.vo2max) : "—"}
          sub="ml/kg/min"
        />
        <Kpi
          label="FC en reposo"
          term="resting_hr"
          value={data.resting_hr ? `${formatNumber(data.resting_hr)}` : "—"}
          sub="ppm"
        />
      </div>

      <div className="grid gap-4 md:gap-6 lg:grid-cols-2">
        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="font-heading text-lg">
              Plan de la semana
            </CardTitle>
            {data.compliance_avg != null && (
              <span className="flex items-center gap-2 text-sm text-muted-foreground">
                Cumplimiento <InfoTerm term="compliance" />
                <ScoreBadge score={data.compliance_avg} />
              </span>
            )}
          </CardHeader>
          <CardContent className="space-y-2">
            {data.planned_this_week.length ? (
              data.planned_this_week.map((p) => {
                const { icon: Icon } = sportInfo(p.sport);
                const weekday = new Date(
                  `${p.day}T12:00:00`,
                ).toLocaleDateString("es-ES", {
                  weekday: "short",
                  day: "numeric",
                });
                return (
                  <Link
                    key={p.id}
                    href={`/plan/${p.id}`}
                    className="flex items-center gap-3 rounded-md bg-muted/60 p-3 hover:bg-muted"
                  >
                    <Icon
                      className="size-5 shrink-0 text-klyp-accent"
                      aria-hidden
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">
                        {p.title}
                      </span>
                      <span className="text-xs text-muted-foreground capitalize">
                        {weekday}
                      </span>
                    </span>
                    {p.compliance_score != null ? (
                      <ScoreBadge score={p.compliance_score} />
                    ) : (
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="size-3" aria-hidden />
                        {p.day < today ? "Sin actividad" : "Pendiente"}
                      </span>
                    )}
                  </Link>
                );
              })
            ) : (
              <p className="text-sm text-muted-foreground">
                No hay sesiones planificadas esta semana.
              </p>
            )}
            <Button asChild variant="outline" className="mt-1 min-h-11 w-full">
              <Link href="/plan">
                <CalendarDays aria-hidden /> Ir al plan
              </Link>
            </Button>
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="font-heading text-lg">
              Últimas actividades
            </CardTitle>
            <Link
              href="/progresion"
              className="flex items-center gap-1 text-sm text-klyp-accent hover:underline"
            >
              Progresión <ArrowRight className="size-4" aria-hidden />
            </Link>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.recent.map((a) => {
              const { icon: Icon, label } = sportInfo(a.sport);
              return (
                <Link
                  key={a.id}
                  href={`/actividades/${a.id}`}
                  className="flex items-center gap-3 rounded-md bg-muted/60 p-3 hover:bg-muted"
                >
                  <Icon
                    className="size-5 shrink-0 text-klyp-accent"
                    aria-label={label}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">
                      {a.name || label}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatDateTime(a.start_time)}
                    </span>
                  </span>
                  <span className="text-right text-sm tabular-nums">
                    {formatDistance(a.distance_m)}
                    <span className="block text-xs text-muted-foreground">
                      {formatDuration(a.duration_s)}
                    </span>
                  </span>
                </Link>
              );
            })}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
