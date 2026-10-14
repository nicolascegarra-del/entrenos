"use client";

import { Info, Trophy } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

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

function Section({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("shadow-sm", className)}>
      <CardHeader>
        <CardTitle className="font-heading text-lg">{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
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

function FitnessSection({ days }: { days: number }) {
  const { data, isPending, isError, refetch } = useFitness(days);
  const { data: devices } = useDevices();
  if (isPending)
    return (
      <Section title="Forma">
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
      <Section title="Forma">
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
      description={`Carga por FC (hrTSS) con umbral ${data.lthr ? `${data.lthr} ppm` : "estimado"} y reposo ${Math.round(data.hr_rest)} ppm.`}
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
      <p className="mt-3 flex gap-1.5 text-xs text-muted-foreground">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        Forma positiva: descansado. Entre −10 y −30: cargado (normal en bloques
        de trabajo). Por debajo de −30: riesgo de sobrecarga.
      </p>
    </Section>
  );
}

function VolumeSection({ days }: { days: number }) {
  const [metric, setMetric] = useState<VolumeMetric>("distance");
  const weeks = Math.ceil(days / 7);
  const { data, isPending, isError, refetch } = useWeekly(weeks);
  const cfg = VOLUME[metric];
  return (
    <Section title="Volumen semanal" className="lg:col-span-2">
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
          xLabel={(v) =>
            `sem. ${new Date(v).toLocaleDateString("es-ES", { day: "numeric", month: "short" })}`
          }
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

function MetricSection({
  title,
  metric,
  days,
  unit,
  color,
  decimals = 0,
  description,
}: {
  title: string;
  metric: string;
  days: number;
  unit: string;
  color: string;
  decimals?: number;
  description?: string;
}) {
  const { data, isPending, isError, refetch } = useMetricSeries(metric, days);
  const { data: devices } = useDevices();
  return (
    <Section title={title} description={description}>
      {isPending ? (
        <Loading />
      ) : isError ? (
        <ErrorState
          message={`No se pudo cargar ${title.toLowerCase()}.`}
          onRetry={() => refetch()}
        />
      ) : data.length < 2 ? (
        <NoData
          text={
            data.length
              ? `Último valor: ${formatNumber(data[0].value, decimals)} ${unit}`
              : undefined
          }
        />
      ) : (
        <TimeChart
          data={data.map((p) => ({ t: t(p.day), value: p.value }))}
          devices={devices}
          unit={unit}
          format={(v) => formatNumber(v, decimals)}
          series={[{ key: "value", label: title, color, kind: "line" }]}
        />
      )}
    </Section>
  );
}

function EfficiencySection({ days }: { days: number }) {
  const { data, isPending, isError, refetch } = useEfficiency(days);
  const { data: devices } = useDevices();
  const trend = data
    ? rollingMean(
        data.map((p) => p.value),
        7,
      )
    : [];
  return (
    <Section
      title="Eficiencia aeróbica"
      description="Metros por minuto por pulsación en carrera: si sube, corres más rápido a la misma FC."
      className="lg:col-span-2"
    >
      {isPending ? (
        <Loading />
      ) : isError ? (
        <ErrorState
          message="No se pudo cargar la eficiencia."
          onRetry={() => refetch()}
        />
      ) : data.length < 2 ? (
        <NoData />
      ) : (
        <TimeChart
          data={data.map((p, i) => ({
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
    </Section>
  );
}

function RecordsSection() {
  const { data, isPending, isError, refetch } = useRecords();
  const withBest = (data ?? []).filter((r) => r.best);
  return (
    <Section
      title="Mejores marcas"
      description="Tramos más rápidos dentro de tus carreras (según Garmin)."
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
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
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
                  {r.history.length > 1 &&
                    ` · mejorada ${r.history.length - 1} ${r.history.length === 2 ? "vez" : "veces"}`}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

export default function ProgresionPage() {
  const [days, setDays] = useState(180);
  const { data: devices } = useDevices();
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
    <section className="space-y-4">
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
      <div className="grid gap-4 md:gap-6 lg:grid-cols-2">
        <FitnessSection days={days} />
        <VolumeSection days={days} />
        <MetricSection
          title="VO2max"
          metric="vo2max"
          days={days}
          unit="ml/kg/min"
          color="var(--chart-4)"
          description="Estimación de Garmin tras cada carrera."
        />
        <MetricSection
          title="FC en reposo"
          metric="resting_hr"
          days={days}
          unit="ppm"
          color="var(--chart-2)"
          description="Más baja suele indicar mejor forma aeróbica o buena recuperación."
        />
        <EfficiencySection days={days} />
        <RecordsSection />
      </div>
    </section>
  );
}
