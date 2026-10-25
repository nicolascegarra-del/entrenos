"use client";

import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  ChevronRight,
  CircleDashed,
  Flame,
  Clock,
  Footprints,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AskCoachCard } from "@/components/assistant/ask-coach-card";
import { CoachNudges } from "@/components/assistant/coach-nudges";
import { InfoTerm } from "@/components/glossary/info-term";
import { PageHeader } from "@/components/layout/page-header";
import { ScoreBadge } from "@/components/plan/status-badge";
import { INSIGHT_STATUS } from "@/components/progress/insight";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { TodayCard } from "@/components/summary/today-card";
import { TourInvite } from "@/components/tour/tour-invite";
import {
  useAchievements,
  useAiProviders,
  useCoachSettings,
  useGarminStatus,
  useGear,
  useGoals,
  useInjuryRisk,
  useLatestReview,
  useProfile,
  useSummary,
  useSources,
} from "@/hooks/use-api";
import {
  formatDateTime,
  formatDistance,
  formatDuration,
  formatNumber,
  sportInfo,
} from "@/lib/format";
import type { GlossaryKey } from "@/lib/glossary";
import { buildNotices, type Notice, setupSteps } from "@/lib/notices";
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

/** Avisos de hoy en una sola tarjeta (Garmin caducado, riesgo de lesión); el resto, plegado. */
function Notices() {
  const { data: injury } = useInjuryRisk();
  const { data: garmin } = useGarminStatus();
  const notices = buildNotices({ garmin, injury });
  if (!notices.length) return null;
  const [first, ...rest] = notices;
  const row = (n: Notice) => {
    const st = INSIGHT_STATUS[n.status];
    return (
      <Link
        key={n.key}
        href={n.href}
        className={cn(
          "flex min-h-11 items-start gap-2 rounded-lg border p-3 text-sm hover:opacity-90",
          st.className,
        )}
      >
        <st.icon className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="font-medium">
            <span className="sr-only">{st.label}: </span>
            {n.title}
          </span>
          {n.message && <span className="block">{n.message}</span>}
        </span>
        <ChevronRight className="mt-0.5 size-4 shrink-0" aria-hidden />
      </Link>
    );
  };
  return (
    <section aria-label="Avisos" className="space-y-2">
      {row(first)}
      {rest.length > 0 && (
        <details>
          <summary className="min-h-11 cursor-pointer content-center text-sm text-muted-foreground">
            {rest.length === 1 ? "1 aviso más" : `${rest.length} avisos más`}
          </summary>
          <div className="mt-2 space-y-2">{rest.map(row)}</div>
        </details>
      )}
    </section>
  );
}

const SETUP_HIDDEN = "hoy.configuracion-oculta";

/** «Completa tu configuración»: lo que falta para sacarle partido (se puede ocultar). */
const FICHA_STEPS = new Set(["interview", "profile", "thresholds"]);

function SetupCard({ hasActivities }: { hasActivities: boolean }) {
  const { data: garmin } = useGarminStatus();
  const { data: goals } = useGoals();
  const { data: gear } = useGear();
  const { data: sources } = useSources();
  const { data: profile } = useProfile();
  const { data: coach } = useCoachSettings();
  const { data: ai } = useAiProviders();
  const hasAi = ai
    ? ai.providers.some((p) => p.configured && p.enabled)
    : undefined;
  const [hidden, setHidden] = useState(true);
  useEffect(() => {
    try {
      setHidden(window.localStorage.getItem(SETUP_HIDDEN) === "1");
    } catch {
      setHidden(false);
    }
  }, []);
  const steps = setupSteps({
    garmin,
    goals,
    gear,
    sources,
    profile,
    coach,
    hasAi,
    hasActivities,
  });
  // La ficha del atleta (entrevista o perfil) no se puede ocultar: sin ella las métricas salen estimadas.
  const shown = hidden ? steps.filter((s) => FICHA_STEPS.has(s.key)) : steps;
  if (!shown.length) return null;
  return (
    <Card className="shadow-sm">
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="font-heading text-base">
          Completa tu configuración
        </CardTitle>
        {!hidden && (
          <Button
            variant="ghost"
            size="sm"
            className="min-h-11 text-muted-foreground md:min-h-8"
            onClick={() => {
              setHidden(true);
              try {
                window.localStorage.setItem(SETUP_HIDDEN, "1");
              } catch {
                // Solo es una comodidad.
              }
            }}
          >
            Ocultar
          </Button>
        )}
      </CardHeader>
      <CardContent>
        <ul className="space-y-1">
          {shown.map((step) => (
            <li key={step.key}>
              <Link
                href={step.href}
                className="flex min-h-11 items-center gap-2 rounded-md px-2 text-sm hover:bg-muted"
              >
                <CircleDashed
                  className="size-4 shrink-0 text-klyp-accent"
                  aria-hidden
                />
                <span className="min-w-0 flex-1 py-1.5">
                  <span className="block">{step.label}</span>
                  {step.hint && (
                    <span className="block text-xs text-muted-foreground">
                      {step.hint}
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
      </CardContent>
    </Card>
  );
}

/** Último análisis de la IA (si lo hay): una línea con su primera frase y enlace al entreno. */
function LatestReviewLine() {
  const { data } = useLatestReview();
  if (!data) return null;
  const first =
    data.content
      .split("\n")
      .map((l) =>
        l
          .replace(/\*\*[^*]+\*\*:?/g, "")
          .replace(/\*\*/g, "")
          .trim(),
      )
      .find((l) => l.length > 20) ?? "";
  return (
    <Link
      href={`/actividades/${data.activity_id}`}
      className="flex min-h-11 items-start gap-3 rounded-lg border p-3 text-sm hover:bg-muted/60"
    >
      <Sparkles
        className="mt-0.5 size-5 shrink-0 text-klyp-accent"
        aria-hidden
      />
      <span className="min-w-0 flex-1">
        <span className="block font-medium">
          Análisis de «{data.activity_name}»
        </span>
        <span className="line-clamp-2 text-muted-foreground">{first}</span>
      </span>
      <ChevronRight
        className="mt-0.5 size-4 shrink-0 text-muted-foreground"
        aria-hidden
      />
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
      data-tour="streak"
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

/** Hoy: cómo llegas, avisos, la semana y lo siguiente que toca. */
export default function HoyPage() {
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
        <PageHeader title="Hoy" hideTitleOnMobile />
        <TourInvite />
        <SetupCard hasActivities={false} />
        <EmptyState icon={Footprints} title="Empieza conectando tu reloj">
          <p className="max-w-sm text-sm text-muted-foreground">
            Sincroniza tus actividades desde{" "}
            <Link
              href="/ajustes/conexiones"
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
  const upcoming = data.planned_this_week
    .filter((p) => p.day >= today || p.compliance_score != null)
    .slice(0, 3);
  return (
    <section className="space-y-4 md:space-y-6">
      <PageHeader title="Hoy" hideTitleOnMobile />
      <TourInvite />

      <div data-tour="today-card">
        <TodayCard summary={data} goals={goals} today={today} />
      </div>
      <AskCoachCard summary={data} today={today} />
      <Notices />
      <LatestReviewLine />
      <CoachNudges />
      <SetupCard hasActivities={data.recent.length > 0} />

      <div className="space-y-2" data-tour="week-kpis">
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
        </div>
        <details className="group">
          <summary className="min-h-11 cursor-pointer content-center text-sm text-klyp-accent">
            <span className="group-open:hidden">
              Ver forma, VO2max y FC en reposo
            </span>
            <span className="hidden group-open:inline">Ocultar</span>
          </summary>
          <div className="mt-2 grid grid-cols-2 gap-2 lg:grid-cols-4">
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
        </details>
      </div>

      <StreakStrip />

      <div className="grid gap-4 md:gap-6 lg:grid-cols-2">
        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="font-heading text-lg">
              Próximas sesiones
            </CardTitle>
            {data.compliance_avg != null && (
              <span className="flex items-center gap-2 text-sm text-muted-foreground">
                Cumplimiento <InfoTerm term="compliance" />
                <ScoreBadge score={data.compliance_avg} />
              </span>
            )}
          </CardHeader>
          <CardContent className="space-y-2">
            {upcoming.length ? (
              upcoming.map((p) => {
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
                    className="flex min-h-11 items-center gap-3 rounded-md bg-muted/60 p-3 hover:bg-muted"
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
                        Pendiente
                      </span>
                    )}
                  </Link>
                );
              })
            ) : (
              <p className="text-sm text-muted-foreground">
                No tienes más sesiones planificadas esta semana.
              </p>
            )}
            <Button asChild variant="outline" className="mt-1 min-h-11 w-full">
              <Link href="/plan">
                <CalendarDays aria-hidden /> Ver el calendario
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
              href="/actividades"
              className="flex min-h-11 items-center gap-1 text-sm text-klyp-accent hover:underline"
            >
              Ver todas <ArrowRight className="size-4" aria-hidden />
            </Link>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.recent.slice(0, 3).map((a) => {
              const { icon: Icon, label } = sportInfo(a.sport);
              return (
                <Link
                  key={a.id}
                  href={`/actividades/${a.id}`}
                  className="flex min-h-11 items-center gap-3 rounded-md bg-muted/60 p-3 hover:bg-muted"
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

      <Link
        href={`/asistente?q=${encodeURIComponent("¿Cómo va mi semana de entrenamiento y qué me recomiendas para los próximos días?")}`}
        className="flex min-h-11 items-center gap-3 rounded-lg border p-3 text-sm hover:bg-muted/60"
      >
        <Sparkles className="size-5 shrink-0 text-klyp-accent" aria-hidden />
        <span className="flex-1">
          <span className="block font-medium">
            Pregúntale a la IA sobre tu semana
          </span>
          <span className="text-xs text-muted-foreground">
            Mira tus entrenos, pulso y zonas, y te explica en qué se basa.
          </span>
        </span>
        <ChevronRight
          className="size-4 shrink-0 text-muted-foreground"
          aria-hidden
        />
      </Link>
    </section>
  );
}
