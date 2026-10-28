"use client";

import { Moon } from "lucide-react";
import { useParams } from "next/navigation";

import { ClockLineChart } from "@/components/health/clock-chart";
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
import { useHealthNight } from "@/hooks/use-api";
import { formatNumber } from "@/lib/format";
import {
  contributorList,
  formatClock,
  formatHm,
  formatTempDelta,
  hasValues,
  hypnogramRuns,
  isIsoDay,
  nightHasData,
  PHASES,
  phaseTotals,
  seriesPoints,
  sleepTimeText,
  sourceLabel,
} from "@/lib/oura";
import type { HealthNight, SleepPeriod } from "@/types/api";

const pct = (v: number | null | undefined) =>
  v == null ? null : `${formatNumber(v)} %`;
const ppm = (v: number | null | undefined) =>
  v == null ? null : `${formatNumber(v)} ppm`;
const hm = (v: number | null | undefined) => (v == null ? null : formatHm(v));

function Hypnogram({ night }: { night: HealthNight }) {
  const runs = hypnogramRuns(night.hypnogram);
  if (!runs.length) return null;
  const totals = phaseTotals(runs);
  return (
    <Block
      title="Hipnograma"
      term="hypnogram"
      description="Fase del sueño cada 5 minutos, de despierto (arriba) a profundo (abajo)."
      className="lg:col-span-2"
    >
      <TimeBands
        ariaLabel={`Hipnograma: ${PHASES.map((p) => `${p.label} ${formatHm(totals[p.key])}`).join(", ")}`}
        lanes={PHASES.map((p) => ({ key: p.key, label: p.label }))}
        bands={runs.map((r) => {
          const meta = PHASES.find((p) => p.key === r.phase)!;
          return {
            lane: r.phase,
            start: r.start,
            end: r.end,
            label: meta.label,
            className: meta.className,
          };
        })}
      />
      <BandLegend
        items={PHASES.map((p) => ({
          key: p.key,
          label: p.label,
          className: p.className,
          sub: formatHm(totals[p.key]),
        }))}
      />
    </Block>
  );
}

function SleepStats({
  main,
  night,
}: {
  main: SleepPeriod;
  night: HealthNight;
}) {
  return (
    <Block title="Resumen de la noche" className="lg:col-span-2">
      <p className="text-sm text-muted-foreground">
        En la cama de {formatClock(new Date(main.bedtime_start).getTime())} a{" "}
        {formatClock(new Date(main.bedtime_end).getTime())}
        {main.time_in_bed_s != null &&
          ` · ${formatHm(main.time_in_bed_s)} en la cama`}
      </p>
      <StatGrid>
        <Stat label="Sueño total" value={hm(main.total_sleep_s)} />
        <Stat label="Profundo" value={hm(main.deep_s)} />
        <Stat label="REM" value={hm(main.rem_s)} />
        <Stat label="Ligero" value={hm(main.light_s)} />
        <Stat label="Despierto" value={hm(main.awake_s)} />
        <Stat label="Tardaste en dormirte" value={hm(main.latency_s)} />
        <Stat label="Eficiencia" value={pct(main.efficiency)} />
        <Stat
          label="Inquietud"
          value={
            main.restless_periods == null
              ? null
              : formatNumber(main.restless_periods)
          }
          sub="periodos de movimiento"
        />
        <Stat label="FC mínima" value={ppm(main.lowest_hr)} />
        <Stat label="FC media" value={ppm(main.avg_hr)} />
        <Stat
          label="HRV media"
          value={
            main.avg_hrv == null ? null : `${formatNumber(main.avg_hrv)} ms`
          }
        />
        <Stat
          label="Respiración"
          value={
            main.avg_breath == null
              ? null
              : `${formatNumber(main.avg_breath, 1)} rpm`
          }
        />
        <Stat
          label="SpO2 media"
          value={
            night.spo2?.average == null
              ? null
              : `${formatNumber(night.spo2.average, 1)} %`
          }
        />
        <Stat
          label="Alteraciones respiratorias"
          term="breathing_disturbance"
          value={
            night.spo2?.breathing_disturbance_index == null
              ? null
              : formatNumber(night.spo2.breathing_disturbance_index)
          }
          sub="por hora"
        />
      </StatGrid>
    </Block>
  );
}

/** Noche que termina en `[dia]`: hipnograma, curvas de FC y HRV, puntuaciones y detalle. */
export default function NochePage() {
  const { dia } = useParams<{ dia: string }>();
  const valid = isIsoDay(dia);
  const { data, isPending, isError, refetch } = useHealthNight(dia, valid);

  const header = (
    <DayNav
      kind="noche"
      day={valid ? dia : ""}
      source={sourceLabel(data?.source)}
    />
  );
  if (!valid)
    return (
      <EmptyState icon={Moon} title="Fecha no válida">
        <p className="text-sm text-muted-foreground">
          Vuelve a Salud y elige una noche.
        </p>
      </EmptyState>
    );
  if (isPending)
    return (
      <div className="space-y-4" role="status" aria-label="Cargando la noche">
        {header}
        <Skeleton className="h-40" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
      </div>
    );
  if (isError)
    return (
      <div className="space-y-4">
        {header}
        <ErrorState
          message="No se pudo cargar esta noche."
          onRetry={() => refetch()}
        />
      </div>
    );
  if (!data || !nightHasData(data))
    return (
      <div className="space-y-4">
        {header}
        <EmptyState icon={Moon} title="Sin datos de esta noche">
          <p className="max-w-sm text-sm text-muted-foreground">
            No llegó nada del anillo ni del reloj. Prueba con otra noche o
            sincroniza desde Ajustes → Conexiones.
          </p>
        </EmptyState>
      </div>
    );

  const hr = seriesPoints(data.hr);
  const hrv = seriesPoints(data.hrv);
  const sleepContribs = contributorList(data.sleep_contributors, "sleep");
  const readiness = data.readiness;
  const readinessContribs = contributorList(
    readiness?.contributors,
    "readiness",
  );
  const sleepTime = sleepTimeText(data.sleep_time);

  return (
    <div className="space-y-4 md:space-y-6">
      {header}
      <div className="grid grid-cols-1 gap-4 md:gap-6 lg:grid-cols-2">
        {(data.sleep_score != null || sleepContribs.length > 0) && (
          <Block title="Puntuación de sueño">
            <Score label="de 100" score={data.sleep_score} />
            <ContributorBars
              items={sleepContribs}
              label="Contribuidores de la puntuación de sueño"
            />
          </Block>
        )}
        {readiness &&
          (readiness.score != null || readinessContribs.length > 0) && (
            <Block title="Recuperación" term="readiness">
              <Score label="de 100" score={readiness.score} />
              <StatGrid>
                <Stat
                  label="Temperatura de la piel"
                  term="skin_temperature"
                  value={
                    readiness.temperature_deviation == null
                      ? null
                      : formatTempDelta(readiness.temperature_deviation)
                  }
                  sub="frente a tu referencia"
                />
                <Stat
                  label="Tendencia de temperatura"
                  value={
                    readiness.temperature_trend_deviation == null
                      ? null
                      : formatTempDelta(readiness.temperature_trend_deviation)
                  }
                  sub="últimos días"
                />
              </StatGrid>
              <ContributorBars
                items={readinessContribs}
                label="Contribuidores de la recuperación"
              />
            </Block>
          )}

        <Hypnogram night={data} />

        {hasValues(hr) && (
          <Block
            title="FC durante la noche"
            description="Pulsaciones por minuto cada 5 minutos."
          >
            <ClockLineChart
              points={hr}
              label="FC"
              unit="ppm"
              color="var(--chart-2)"
            />
          </Block>
        )}
        {hasValues(hrv) && (
          <Block
            title="HRV durante la noche"
            description="Variabilidad de la frecuencia cardiaca (RMSSD) cada 5 minutos."
          >
            <ClockLineChart
              points={hrv}
              label="HRV"
              unit="ms"
              color="var(--chart-3)"
            />
          </Block>
        )}

        {data.main && <SleepStats main={data.main} night={data} />}

        {sleepTime && (
          <Block title="Horario recomendado">
            {sleepTime.window && (
              <p className="text-lg font-semibold">{sleepTime.window}</p>
            )}
            {sleepTime.status && (
              <p className="text-sm text-muted-foreground">
                {sleepTime.status}
              </p>
            )}
            {sleepTime.recommendation && (
              <p className="text-sm">{sleepTime.recommendation}</p>
            )}
          </Block>
        )}

        {data.naps.length > 0 && (
          <Block title="Siestas">
            <ul className="space-y-2">
              {data.naps.map((n) => (
                <li
                  key={n.bedtime_start}
                  className="flex items-center justify-between gap-2 rounded-md bg-muted/60 p-3 text-sm"
                >
                  <span>
                    {formatClock(new Date(n.bedtime_start).getTime())}–
                    {formatClock(new Date(n.bedtime_end).getTime())}
                  </span>
                  <span className="tabular-nums">
                    {formatHm(n.total_sleep_s)}
                    {n.avg_hr != null && (
                      <span className="text-muted-foreground">
                        {" "}
                        · {formatNumber(n.avg_hr)} ppm
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
