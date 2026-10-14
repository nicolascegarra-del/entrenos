"use client";

import { ShieldAlert, Trophy } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { INSIGHT_STATUS, InsightCallout } from "@/components/progress/insight";
import { TimeChart, rollingMean } from "@/components/progress/time-chart";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useDevices,
  useEfficiency,
  useFitness,
  useInsights,
  useMetricSeries,
  useRecords,
  useWeekly,
} from "@/hooks/use-api";
import {
  formatDate,
  formatDuration,
  formatNumber,
  formatPace,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Insight, InsightSection, InsightsResponse } from "@/types/api";

const PERIODS = [
  { label: "3 meses", days: 90 },
  { label: "6 meses", days: 180 },
  { label: "1 año", days: 365 },
  { label: "2 años", days: 730 },
];

type VolumeMetric = "distance" | "duration" | "load";
const VOLUME: Record<
  VolumeMetric,
  {
    label: string;
    unit: string;
    get: (w: {
      distance_m: number;
      duration_s: number;
      load: number;
    }) => number;
    format: (v: number) => string;
  }
> = {
  distance: {
    label: "Kilómetros",
    unit: "km",
    get: (w) => w.distance_m / 1000,
    format: (v) => formatNumber(v, 0),
  },
  duration: {
    label: "Horas",
    unit: "h",
    get: (w) => w.duration_s / 3600,
    format: (v) => formatNumber(v, 1),
  },
  load: {
    label: "Carga",
    unit: "",
    get: (w) => w.load,
    format: (v) => formatNumber(v, 0),
  },
};

const t = (iso: string) => new Date(`${iso}T12:00:00`).getTime();
const weekLabel = (v: number) =>
  `sem. ${new Date(v).toLocaleDateString("es-ES", { day: "numeric", month: "short" })}`;

function Section({
  title,
  description,
  insight,
  children,
  className,
}: {
  title: string;
  description?: string;
  insight?: Insight;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("shadow-sm", className)}>
      <CardHeader>
        <CardTitle className="font-heading text-lg">{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        {children}
        <InsightCallout insight={insight} />
      </CardContent>
    </Card>
  );
}

function Loading() {
  return <Skeleton className="h-48 w-full" />;
}

function NoData({
  text = "Aún no hay datos en este periodo.",
}: {
  text?: string;
}) {
  return (
    <p className="py-10 text-center text-sm text-muted-foreground">{text}</p>
  );
}

type Sections = Partial<Record<InsightSection, Insight>>;

/** Semáforo de 4 señales que resume el análisis. */
function OverallPanel({ data }: { data?: InsightsResponse }) {
  if (!data) return <Skeleton className="h-24 w-full" />;
  return (
    <section aria-labelledby="estado-general" className="space-y-2">
      <h2 id="estado-general" className="font-heading text-lg font-semibold">
        Estado general
      </h2>
      <ul className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        {data.overall.map((g) => {
          const { icon: Icon, label, className } = INSIGHT_STATUS[g.status];
          return (
            <li
              key={g.label}
              className={cn("rounded-lg border p-3", className)}
            >
              <p className="flex items-center gap-1.5 text-xs font-medium">
                <Icon className="size-4" aria-hidden /> {g.label}
                <span className="sr-only">: {label}</span>
              </p>
              <p className="mt-1 text-sm font-semibold">{g.title}</p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function FitnessSection({
  days,
  insight,
}: {
  days: number;
  insight?: Insight;
}) {
  const { data, isPending, isError, refetch } = useFitness(days);
  const { data: devices } = useDevices();
  if (isPending)
    return (
      <Section title="Forma" className="lg:col-span-2">
        <Loading />
      </Section>
    );
  if (isError)
    return (
      <ErrorState
        message="No se pudo calcular la forma."
        onRetry={() => refetch()}
      />
    );
  if (!data.points.length)
    return (
      <Section title="Forma" insight={insight} className="lg:col-span-2">
        <NoData />
      </Section>
    );
  const rows = data.points.map((p) => ({
    t: t(p.day),
    ctl: p.ctl,
    atl: p.atl,
    tsb: p.tsb,
  }));
  const last = data.points[data.points.length - 1];
  return (
    <Section
      title="Forma"
      description={`Carga por FC (hrTSS) con umbral ${data.lthr ? `${data.lthr} ppm` : "estimado"} y reposo ${Math.round(data.hr_rest)} ppm; sin FC, por RPE.`}
      insight={insight}
      className="lg:col-span-2"
    >
      <div className="mb-4 grid grid-cols-3 gap-2">
        {[
          { label: "Fitness (CTL)", value: last.ctl },
          { label: "Fatiga (ATL)", value: last.atl },
          { label: "Forma (TSB)", value: last.tsb },
        ].map((k) => (
          <div key={k.label} className="rounded-lg bg-muted/60 p-3">
            <p className="text-xs text-muted-foreground">{k.label}</p>
            <p className="text-xl font-semibold tabular-nums">
              {formatNumber(k.value)}
            </p>
          </div>
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <figure>
          <figcaption className="mb-1 text-sm font-medium">
            Fitness y fatiga
          </figcaption>
          <TimeChart
            data={rows}
            devices={devices}
            format={(v) => formatNumber(v)}
            series={[
              {
                key: "ctl",
                label: "Fitness (42 d)",
                color: "var(--chart-1)",
                kind: "line",
              },
              {
                key: "atl",
                label: "Fatiga (7 d)",
                color: "var(--chart-2)",
                kind: "line",
              },
            ]}
          />
        </figure>
        <figure>
          <figcaption className="mb-1 text-sm font-medium">
            Forma = fitness − fatiga
          </figcaption>
          <TimeChart
            data={rows}
            devices={devices}
            zeroLine
            format={(v) => formatNumber(v)}
            series={[
              {
                key: "tsb",
                label: "Forma",
                color: "var(--chart-3)",
                kind: "area",
              },
            ]}
          />
        </figure>
      </div>
    </Section>
  );
}

function AcwrSection({
  data,
  insight,
}: {
  data?: InsightsResponse;
  insight?: Insight;
}) {
  const rows = (data?.acwr ?? []).map((p) => ({ t: t(p.day), value: p.acwr }));
  return (
    <Section
      title="Carga aguda : crónica"
      description="Carga de los últimos 7 días frente a la de los últimos 28 (medias exponenciales)."
      insight={insight}
    >
      {!data ? (
        <Loading />
      ) : rows.filter((r) => r.value != null).length < 2 ? (
        <NoData />
      ) : (
        <TimeChart
          data={rows}
          format={(v) => formatNumber(v, 1)}
          band={{ from: 0.8, to: 1.3, label: "zona habitual 0,8–1,3" }}
          series={[
            {
              key: "value",
              label: "ACWR",
              color: "var(--chart-1)",
              kind: "line",
            },
          ]}
        />
      )}
    </Section>
  );
}

function VolumeSection({ days, insight }: { days: number; insight?: Insight }) {
  const [metric, setMetric] = useState<VolumeMetric>("distance");
  const { data, isPending, isError, refetch } = useWeekly(Math.ceil(days / 7));
  const cfg = VOLUME[metric];
  return (
    <Section title="Volumen semanal" insight={insight}>
      <div
        className="mb-3 flex gap-1"
        role="group"
        aria-label="Métrica de volumen"
      >
        {(Object.keys(VOLUME) as VolumeMetric[]).map((m) => (
          <Button
            key={m}
            size="sm"
            variant={metric === m ? "default" : "outline"}
            aria-pressed={metric === m}
            className="min-h-11 md:min-h-8"
            onClick={() => setMetric(m)}
          >
            {VOLUME[m].label}
          </Button>
        ))}
      </div>
      {isPending ? (
        <Loading />
      ) : isError ? (
        <ErrorState
          message="No se pudo cargar el volumen."
          onRetry={() => refetch()}
        />
      ) : (
        <TimeChart
          data={data.map((w) => ({
            t: t(w.week),
            value: Math.round(cfg.get(w) * 10) / 10,
          }))}
          format={cfg.format}
          unit={cfg.unit}
          xLabel={weekLabel}
          series={[
            {
              key: "value",
              label: cfg.label,
              color: "var(--chart-1)",
              kind: "bar",
            },
          ]}
        />
      )}
    </Section>
  );
}

function IntensitySection({
  data,
  insight,
}: {
  data?: InsightsResponse;
  insight?: Insight;
}) {
  const weeks = data?.intensity.weeks ?? [];
  const split = data?.intensity.split_min;
  const total = split ? split.low + split.moderate + split.high : 0;
  return (
    <Section
      title="Distribución de intensidad"
      description="Minutos por semana en zonas de FC: suave (Z1–Z2), moderada (Z3) e intensa (Z4–Z5)."
      insight={insight}
    >
      {!data ? (
        <Loading />
      ) : !total ? (
        <NoData />
      ) : (
        <>
          <div
            className="mb-3 flex h-3 overflow-hidden rounded-full"
            aria-hidden
          >
            <span
              style={{
                width: `${(split!.low / total) * 100}%`,
                background: "var(--intensity-low)",
              }}
            />
            <span
              style={{
                width: `${(split!.moderate / total) * 100}%`,
                background: "var(--intensity-mid)",
              }}
            />
            <span
              style={{
                width: `${(split!.high / total) * 100}%`,
                background: "var(--intensity-high)",
              }}
            />
          </div>
          <TimeChart
            data={weeks.map((w) => ({
              t: t(w.week),
              low: w.low,
              moderate: w.moderate,
              high: w.high,
            }))}
            format={(v) => formatNumber(v)}
            unit="min"
            xLabel={weekLabel}
            series={[
              {
                key: "low",
                label: "Suave",
                color: "var(--intensity-low)",
                kind: "bar",
                stack: "z",
              },
              {
                key: "moderate",
                label: "Moderada",
                color: "var(--intensity-mid)",
                kind: "bar",
                stack: "z",
              },
              {
                key: "high",
                label: "Intensa",
                color: "var(--intensity-high)",
                kind: "bar",
                stack: "z",
              },
            ]}
          />
        </>
      )}
    </Section>
  );
}

function MetricSection({
  title,
  metric,
  days,
  unit,
  color,
  decimals = 0,
  description,
  insight,
  transform = (v) => v,
}: {
  title: string;
  metric: string;
  days: number;
  unit: string;
  color: string;
  decimals?: number;
  description?: string;
  insight?: Insight;
  transform?: (v: number) => number;
}) {
  const { data, isPending, isError, refetch } = useMetricSeries(metric, days);
  const { data: devices } = useDevices();
  return (
    <Section title={title} description={description} insight={insight}>
      {isPending ? (
        <Loading />
      ) : isError ? (
        <ErrorState
          message={`No se pudo cargar ${title.toLowerCase()}.`}
          onRetry={() => refetch()}
        />
      ) : data.length < 2 ? (
        <NoData />
      ) : (
        <TimeChart
          data={data.map((p) => ({ t: t(p.day), value: transform(p.value) }))}
          devices={devices}
          unit={unit}
          format={(v) => formatNumber(v, decimals)}
          series={[{ key: "value", label: title, color, kind: "line" }]}
        />
      )}
    </Section>
  );
}

function EfficiencySection({
  days,
  insight,
  data,
}: {
  days: number;
  insight?: Insight;
  data?: InsightsResponse;
}) {
  const { data: points, isPending, isError, refetch } = useEfficiency(days);
  const { data: devices } = useDevices();
  const trend = points
    ? rollingMean(
        points.map((p) => p.value),
        7,
      )
    : [];
  const decoupling = data?.decoupling ?? [];
  return (
    <Section
      title="Eficiencia aeróbica"
      description="Metros por minuto por pulsación en carrera: si sube, corres más rápido a la misma FC."
      insight={insight}
      className="lg:col-span-2"
    >
      {isPending ? (
        <Loading />
      ) : isError ? (
        <ErrorState
          message="No se pudo cargar la eficiencia."
          onRetry={() => refetch()}
        />
      ) : points.length < 2 ? (
        <NoData />
      ) : (
        <TimeChart
          data={points.map((p, i) => ({
            t: t(p.day),
            value: p.value,
            trend: trend[i],
          }))}
          devices={devices}
          format={(v) => formatNumber(v, 2)}
          series={[
            {
              key: "value",
              label: "Carrera",
              color: "var(--chart-5)",
              kind: "dots",
            },
            {
              key: "trend",
              label: "Tendencia (7 carreras)",
              color: "var(--chart-3)",
              kind: "line",
            },
          ]}
        />
      )}
      {decoupling.length > 0 && (
        <div className="mt-3">
          <p className="text-sm font-medium">
            Desacople en rodajes largos a ritmo constante
          </p>
          <ul className="mt-1 flex flex-wrap gap-2">
            {decoupling.map((d) => (
              <li key={d.activity_id}>
                <Link
                  href={`/actividades/${d.activity_id}`}
                  className="inline-flex min-h-11 items-center rounded-md bg-muted/60 px-3 text-xs tabular-nums hover:bg-muted md:min-h-8"
                >
                  {formatDate(`${d.day}T12:00:00`)} · {formatNumber(d.value, 1)}{" "}
                  %
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Section>
  );
}

function RecordsSection({
  insight,
  data,
}: {
  insight?: Insight;
  data?: InsightsResponse;
}) {
  const { data: records, isPending, isError, refetch } = useRecords();
  const withBest = (records ?? []).filter((r) => r.best);
  const paces = data?.training_paces;
  return (
    <Section
      title="Mejores marcas y predicciones"
      description="Tramos más rápidos dentro de tus carreras (según Garmin)."
      insight={insight}
      className="lg:col-span-2"
    >
      {isPending ? (
        <Loading />
      ) : isError ? (
        <ErrorState
          message="No se pudieron cargar las marcas."
          onRetry={() => refetch()}
        />
      ) : !withBest.length ? (
        <NoData text="Aún no hay marcas registradas." />
      ) : (
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {withBest.map((r) => (
            <li key={r.key}>
              <Link
                href={`/actividades/${r.best!.activity_id}`}
                className="block rounded-lg bg-muted/60 p-3 hover:bg-muted"
              >
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Trophy className="size-3.5 text-klyp-accent" aria-hidden />{" "}
                  {r.label}
                </p>
                <p className="mt-0.5 text-xl font-semibold tabular-nums">
                  {formatDuration(r.best!.time_s)}
                </p>
                <p className="text-xs text-muted-foreground tabular-nums">
                  {formatPace(r.distance_m / r.best!.time_s)} ·{" "}
                  {formatDate(`${r.best!.day}T12:00:00`)}
                </p>
                {r.age_grade && (
                  <p className="text-xs text-muted-foreground tabular-nums">
                    {formatNumber(r.age_grade.percent, 1)} % ajustado por edad ·{" "}
                    {r.age_grade.level}
                  </p>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
      {data && data.predictions.length > 0 && (
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <p className="mb-2 text-sm font-medium">
              Tiempos estimados (Riegel)
            </p>
            <ul className="space-y-1 text-sm">
              {data.predictions.map((p) => (
                <li
                  key={p.label}
                  className="flex justify-between gap-2 rounded-md bg-muted/60 px-3 py-2 tabular-nums"
                >
                  <span>{p.label}</span>
                  <span>
                    {formatDuration(p.time_s)}{" "}
                    <span className="text-muted-foreground">
                      ({formatDuration(p.pace_s_km)} /km)
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
          {paces && (
            <div>
              <p className="mb-2 text-sm font-medium">
                Ritmos de entrenamiento (VDOT)
              </p>
              <ul className="space-y-1 text-sm">
                {[
                  {
                    label: "Rodaje suave",
                    value: `${formatDuration(paces.easy[0])}–${formatDuration(paces.easy[1])}`,
                  },
                  {
                    label: "Umbral (tempo)",
                    value: formatDuration(paces.threshold),
                  },
                  {
                    label: "Intervalos (VO2max)",
                    value: formatDuration(paces.interval),
                  },
                ].map((p) => (
                  <li
                    key={p.label}
                    className="flex justify-between gap-2 rounded-md bg-muted/60 px-3 py-2 tabular-nums"
                  >
                    <span>{p.label}</span>
                    <span>{p.value} /km</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Section>
  );
}

export default function ProgresionPage() {
  const [days, setDays] = useState(180);
  const { data: devices } = useDevices();
  const { data: insights } = useInsights(days);
  const s: Sections = insights?.sections ?? {};

  if (devices && devices.length === 0) {
    return (
      <section className="space-y-4">
        <h1 className="font-heading text-2xl font-bold md:text-3xl">
          Progresión
        </h1>
        <EmptyState icon={Trophy} title="Aún no hay actividades">
          <p className="text-sm text-muted-foreground">
            Sincroniza Garmin desde{" "}
            <Link
              href="/ajustes"
              className="font-medium text-klyp-accent underline"
            >
              Ajustes
            </Link>{" "}
            para ver tu evolución.
          </p>
        </EmptyState>
      </section>
    );
  }
  return (
    <section className="space-y-4 md:space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-heading text-2xl font-bold md:text-3xl">
          Progresión
        </h1>
        <div
          className="flex gap-1 overflow-x-auto"
          role="group"
          aria-label="Periodo"
        >
          {PERIODS.map((p) => (
            <Button
              key={p.days}
              size="sm"
              variant={days === p.days ? "default" : "outline"}
              aria-pressed={days === p.days}
              className="min-h-11 shrink-0 md:min-h-8"
              onClick={() => setDays(p.days)}
            >
              {p.label}
            </Button>
          ))}
        </div>
      </div>

      <OverallPanel data={insights} />

      <div className="grid gap-4 md:gap-6 lg:grid-cols-2">
        <FitnessSection days={days} insight={s.fitness} />
        <AcwrSection data={insights} insight={s.acwr} />
        <VolumeSection days={days} insight={s.volume} />
        <IntensitySection data={insights} insight={s.intensity} />
        <MetricSection
          title="FC en reposo"
          metric="resting_hr"
          days={days}
          unit="ppm"
          color="var(--chart-2)"
          description="Comparada con tu propia referencia de los últimos 30 días."
          insight={s.resting_hr}
        />
        <MetricSection
          title="VO2max"
          metric="vo2max"
          days={days}
          unit="ml/kg/min"
          color="var(--chart-4)"
          description="Estimación de Garmin tras cada carrera."
          insight={s.vo2max}
        />
        <MetricSection
          title="Sueño"
          metric="sleep_seconds"
          days={Math.min(days, 120)}
          unit="h"
          decimals={1}
          color="var(--chart-1)"
          transform={(v) => v / 3600}
          description="Horas por noche (Garmin)."
          insight={s.recovery}
        />
        <Section
          title="Constancia"
          description="Regularidad de las últimas 4 semanas."
          insight={s.consistency}
          className="lg:col-span-2"
        />
        <EfficiencySection days={days} insight={s.efficiency} data={insights} />
        <RecordsSection insight={s.records} data={insights} />
      </div>

      {insights && (
        <p className="flex items-start gap-2 text-xs text-muted-foreground">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          {insights.disclaimer}
        </p>
      )}
    </section>
  );
}
