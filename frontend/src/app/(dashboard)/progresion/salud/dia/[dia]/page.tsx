"use client";

import { BedDouble, CalendarDays, Wind } from "lucide-react";
import { useParams } from "next/navigation";

import {
  ClockLineChart,
  HeartRateDayChart,
} from "@/components/health/clock-chart";
import { DayNav } from "@/components/health/day-nav";
import {
  Block,
  ContributorBars,
  Score,
  Stat,
  StatGrid,
  Tags,
} from "@/components/health/health-ui";
import { BandLegend, TimeBands } from "@/components/health/time-bands";
import { EmptyState, ErrorState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useHealthDay } from "@/hooks/use-api";
import { formatNumber } from "@/lib/format";
import {
  ACTIVITY_CLASSES,
  activityRuns,
  contributorList,
  dayHasData,
  formatClock,
  formatDayShort,
  formatHm,
  hasValues,
  heartRateByOrigin,
  HR_ORIGINS,
  isIsoDay,
  moodLabel,
  resilienceLabel,
  seriesPoints,
  sessionLabel,
  stressSummaryLabel,
} from "@/lib/oura";
import type { HealthDay } from "@/types/api";

const hm = (v: number | null | undefined) => (v == null ? null : formatHm(v));
const kcal = (v: number | null | undefined) =>
  v == null ? null : `${formatNumber(v)} kcal`;

function ActivityProfile({
  activity,
}: {
  activity: NonNullable<HealthDay["activity"]>;
}) {
  const runs = activityRuns(activity.class_5min);
  if (!runs.length) return null;
  const meta = new Map(ACTIVITY_CLASSES.map((c) => [c.code, c]));
  const used = new Set(runs.map((r) => r.code));
  return (
    <Block
      title="Perfil de actividad"
      description="Cómo de activo estuviste cada 5 minutos."
      className="lg:col-span-2"
    >
      <TimeBands
        ariaLabel="Perfil de actividad del día cada 5 minutos"
        lanes={[{ key: "actividad", label: "Actividad" }]}
        showLaneLabels={false}
        laneHeight="h-10"
        bands={runs.map((r) => ({
          lane: "actividad",
          start: r.start,
          end: r.end,
          label: meta.get(r.code)!.label,
          className: meta.get(r.code)!.className,
        }))}
      />
      <BandLegend
        items={ACTIVITY_CLASSES.filter((c) => used.has(c.code)).map((c) => ({
          key: c.code,
          label: c.label,
          className: c.className,
        }))}
      />
    </Block>
  );
}

/** Día `[dia]`: FC continua por origen, actividad, MET, estrés, resiliencia, sesiones y etiquetas. */
export default function DiaPage() {
  const { dia } = useParams<{ dia: string }>();
  const valid = isIsoDay(dia);
  const { data, isPending, isError, refetch } = useHealthDay(dia, valid);

  if (!valid)
    return (
      <EmptyState icon={CalendarDays} title="Fecha no válida">
        <p className="text-sm text-muted-foreground">
          Vuelve a Salud y elige un día.
        </p>
      </EmptyState>
    );
  const header = <DayNav kind="dia" day={dia} />;
  if (isPending)
    return (
      <div className="space-y-4" role="status" aria-label="Cargando el día">
        {header}
        <Skeleton className="h-56" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      </div>
    );
  if (isError)
    return (
      <div className="space-y-4">
        {header}
        <ErrorState
          message="No se pudo cargar este día."
          onRetry={() => refetch()}
        />
      </div>
    );
  if (!data || !dayHasData(data))
    return (
      <div className="space-y-4">
        {header}
        <EmptyState icon={CalendarDays} title="Sin datos de este día">
          <p className="max-w-sm text-sm text-muted-foreground">
            No llegó nada del anillo ni del reloj. Prueba con otro día o
            sincroniza desde Ajustes → Conexiones.
          </p>
        </EmptyState>
      </div>
    );

  const groups = heartRateByOrigin(data.heartrate);
  const hrGroups = HR_ORIGINS.map((o) => ({ ...o, points: groups[o.key] }));
  const hasHr = hrGroups.some((g) => g.points.length);
  const a = data.activity;
  const met = seriesPoints(a?.met);
  const resilienceContribs = contributorList(
    data.resilience?.contributors,
    "resilience",
  );
  const stress = data.stress;

  return (
    <div className="space-y-4 md:space-y-6">
      {header}
      {data.rest_mode && (
        <p className="flex items-start gap-2 rounded-lg border border-klyp-accent/40 bg-klyp-accent/5 p-3 text-sm">
          <BedDouble
            className="mt-0.5 size-4 shrink-0 text-klyp-accent"
            aria-hidden
          />
          <span>
            <span className="font-medium">Modo descanso</span> desde el{" "}
            {formatDayShort(data.rest_mode.start_date)}
            {data.rest_mode.end_date
              ? ` hasta el ${formatDayShort(data.rest_mode.end_date)}`
              : " (sigue activo)"}
            . Oura no te pide actividad estos días.
          </span>
        </p>
      )}
      <div className="grid grid-cols-1 gap-4 md:gap-6 lg:grid-cols-2">
        {hasHr && (
          <Block
            title="FC a lo largo del día"
            description="Una muestra por minuto, coloreada según lo que estabas haciendo."
            className="lg:col-span-2"
          >
            <HeartRateDayChart groups={hrGroups} />
          </Block>
        )}

        {a && <ActivityProfile activity={a} />}

        {a && (
          <Block title="Actividad">
            <Score label="puntuación de actividad" score={a.score} />
            <StatGrid>
              <Stat
                label="Pasos"
                value={a.steps == null ? null : formatNumber(a.steps)}
              />
              <Stat label="Calorías activas" value={kcal(a.active_calories)} />
              <Stat label="Calorías totales" value={kcal(a.total_calories)} />
              <Stat label="Intensidad alta" value={hm(a.high_s)} />
              <Stat label="Intensidad media" value={hm(a.medium_s)} />
              <Stat label="Intensidad baja" value={hm(a.low_s)} />
              <Stat label="Sentado o quieto" value={hm(a.sedentary_s)} />
              <Stat label="Sin el anillo" value={hm(a.non_wear_s)} />
            </StatGrid>
          </Block>
        )}

        {hasValues(met) && (
          <Block
            title="Gasto energético (MET)"
            description="1 MET es estar en reposo; caminar rápido son unos 4 y correr, 8 o más."
          >
            <ClockLineChart
              points={met}
              label="MET"
              unit="MET"
              color="var(--chart-1)"
              format={(v) => formatNumber(v, 1)}
            />
          </Block>
        )}

        {(stress || data.resilience) && (
          <Block title="Estrés y recuperación" term="resilience">
            {stress?.day_summary && (
              <p className="font-medium">
                {stressSummaryLabel(stress.day_summary)}
              </p>
            )}
            <StatGrid>
              <Stat label="Estrés alto" value={hm(stress?.stress_high_s)} />
              <Stat
                label="Recuperación alta"
                value={hm(stress?.recovery_high_s)}
              />
              <Stat
                label="Resiliencia"
                term="resilience"
                value={
                  data.resilience?.level
                    ? resilienceLabel(data.resilience.level)
                    : null
                }
              />
            </StatGrid>
            <ContributorBars
              items={resilienceContribs}
              label="Contribuidores de la resiliencia"
            />
          </Block>
        )}

        {data.sessions.length > 0 && (
          <Block title="Sesiones de bienestar">
            <ul className="space-y-2">
              {data.sessions.map((s) => (
                <li
                  key={s.start}
                  className="flex items-start gap-3 rounded-md bg-muted/60 p-3 text-sm"
                >
                  <Wind
                    className="mt-0.5 size-4 shrink-0 text-klyp-accent"
                    aria-hidden
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">
                      {sessionLabel(s.type)}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatClock(new Date(s.start).getTime())}–
                      {formatClock(new Date(s.end).getTime())}
                      {moodLabel(s.mood) && ` · ánimo: ${moodLabel(s.mood)}`}
                    </span>
                  </span>
                  <span className="text-right text-xs tabular-nums text-muted-foreground">
                    {s.hr_avg != null && (
                      <span className="block">
                        {formatNumber(s.hr_avg)} ppm
                      </span>
                    )}
                    {s.hrv_avg != null && (
                      <span className="block">
                        HRV {formatNumber(s.hrv_avg)} ms
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </Block>
        )}

        <Tags tags={data.tags} />
      </div>
    </div>
  );
}
