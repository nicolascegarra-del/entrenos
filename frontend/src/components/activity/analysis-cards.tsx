"use client";

import { Activity as ActivityIcon, Gauge, HeartPulse } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useActivityAnalysis } from "@/hooks/use-api";
import { formatDate, formatDuration } from "@/lib/format";
import type { ActivityAnalysis } from "@/types/api";

const axisTick = { fontSize: 11, fill: "var(--muted-foreground)" };
const tooltipStyle = {
  background: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
  color: "var(--popover-foreground)",
};
// Zonas ordenadas de suave a intensa: un solo tono, de claro a oscuro.
const ZONE_SHADES = [35, 50, 65, 82, 100];
const zoneColor = (i: number) =>
  `color-mix(in oklab, var(--chart-1) ${ZONE_SHADES[i] ?? 100}%, var(--card))`;

const minutes = (s: number) =>
  s >= 3600 ? formatDuration(s) : `${Math.round(s / 60)} min`;

/** Tiempo en cada zona de FC: barras horizontales con minutos y % y la tabla de rangos. */
function HrZonesCard({ data }: { data: ActivityAnalysis["hr_zones"] }) {
  const rows = data.zones.map((z, i) => ({
    ...z,
    label: z.name.split(" ")[0],
    color: zoneColor(i),
  }));
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <HeartPulse className="size-5 text-klyp-accent" aria-hidden /> Zonas
          de FC
        </CardTitle>
        <CardDescription>
          Tiempo en cada zona ({data.source}
          {data.lthr ? `, umbral ${Math.round(data.lthr)} ppm` : ""}).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <figure
          className="h-48"
          aria-label="Tiempo en cada zona de frecuencia cardiaca"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={rows}
              layout="vertical"
              margin={{ top: 0, right: 72, bottom: 0, left: 0 }}
              barCategoryGap={4}
            >
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="label"
                width={32}
                tick={axisTick}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                cursor={{ fill: "var(--muted)" }}
                contentStyle={tooltipStyle}
                formatter={(v: number) => [minutes(v), "Tiempo"]}
                labelFormatter={(_, p) => p?.[0]?.payload?.name ?? ""}
              />
              <Bar
                dataKey="seconds"
                radius={[0, 4, 4, 0]}
                isAnimationActive={false}
              >
                {rows.map((r) => (
                  <Cell key={r.name} fill={r.color} />
                ))}
                <LabelList
                  dataKey="seconds"
                  position="right"
                  content={({ x, y, width, height, index }) => {
                    const r = rows[index as number];
                    return (
                      <text
                        x={Number(x) + Number(width) + 6}
                        y={Number(y) + Number(height) / 2}
                        dominantBaseline="middle"
                        fontSize={11}
                        fill="var(--foreground)"
                      >
                        {minutes(r.seconds)} · {r.pct.toLocaleString("es-ES")} %
                      </text>
                    );
                  }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </figure>
        <table className="w-full text-sm tabular-nums">
          <caption className="sr-only">
            Zonas de FC y tiempo en cada una
          </caption>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} className="border-t">
                <td className="py-1">
                  <span
                    className="mr-2 inline-block size-2.5 rounded-sm align-middle"
                    style={{ background: r.color }}
                    aria-hidden
                  />
                  {r.name}
                </td>
                <td className="py-1 text-muted-foreground">
                  {r.max ? `${r.min}–${r.max}` : `${r.min}+`} ppm
                </td>
                <td className="py-1 text-right">{minutes(r.seconds)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

/** VO2max de la actividad (del reloj o estimado) y el actual, con su percentil. */
function Vo2maxCard({ data }: { data: ActivityAnalysis["vo2max"] }) {
  const p = data.percentile;
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <Gauge className="size-5 text-klyp-accent" aria-hidden /> VO2max
        </CardTitle>
        <CardDescription>
          El consumo máximo de oxígeno: tu «motor» aeróbico.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {data.activity ? (
          <div>
            <p className="font-heading text-4xl font-bold tabular-nums">
              {data.activity.toLocaleString("es-ES", {
                maximumFractionDigits: 1,
              })}
              <span className="ml-1 text-base font-normal text-muted-foreground">
                ml/kg/min
              </span>
            </p>
            <p className="text-sm text-muted-foreground">
              {data.source === "reloj"
                ? "Calculado por tu reloj en esta actividad."
                : "Estimado por la app con tu ritmo y FC de esta carrera (orientativo: mejor en llano y a ritmo constante)."}
            </p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Esta actividad no da para estimarlo: hace falta una carrera
            sostenida de al menos 15 min, en llano y con pulso.
          </p>
        )}
        {data.current && (
          <p className="text-sm">
            Tu VO2max actual:{" "}
            <strong className="tabular-nums">
              {data.current.toLocaleString("es-ES", {
                maximumFractionDigits: 1,
              })}
            </strong>
            {data.current_day ? ` (${formatDate(data.current_day)})` : ""}.
          </p>
        )}
        {p && (
          <p className="text-sm text-muted-foreground">
            Para tu edad ({p.age_group} años) estás{" "}
            {p.bound === "below"
              ? "por debajo del percentil 5"
              : p.bound === "above"
                ? "por encima del percentil 95"
                : `en el percentil ${Math.round(p.percentile)}`}
            {` (la mediana es ${p.median.toLocaleString("es-ES")})`}.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

const DRIFT_TEXT: Record<string, string> = {
  bien: "Tu FC se mantuvo estable para el ritmo: buena base aeróbica.",
  alta: "Tu FC subió para el mismo ritmo en la 2.ª mitad: calor, deshidratación o falta de fondo.",
  "muy alta":
    "La FC se disparó en la 2.ª mitad: el ritmo fue alto para tu base aeróbica actual (o hizo mucho calor).",
};

/** Parciales por km (barra más larga = km más rápido) y deriva cardiaca. */
function SplitsCard({ data }: { data: ActivityAnalysis }) {
  const rows = data.splits.map((s) => ({
    ...s,
    label: s.distance_m < 990 ? `${s.km}*` : String(s.km),
    speed: s.distance_m / s.seconds,
  }));
  const best = Math.min(...rows.map((r) => r.pace_s_km));
  const drift = data.decoupling;
  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-heading text-lg">
          <ActivityIcon className="size-5 text-klyp-accent" aria-hidden />{" "}
          Parciales por km
        </CardTitle>
        <CardDescription>
          Barra más larga = km más rápido. El más rápido va resaltado.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {drift && (
          <div className="rounded-lg bg-muted/60 p-3">
            <p className="text-sm">
              <span className="font-medium">Deriva cardiaca:</span>{" "}
              <span className="font-heading text-lg font-semibold tabular-nums">
                {drift.pct.toLocaleString("es-ES")} %
              </span>{" "}
              <span className="text-muted-foreground">({drift.level})</span>
            </p>
            <p className="text-xs text-muted-foreground">
              {DRIFT_TEXT[drift.level]} Por debajo del 5 % es lo ideal en
              rodajes largos.
            </p>
          </div>
        )}
        <figure
          style={{ height: Math.max(120, rows.length * 26 + 16) }}
          aria-label="Ritmo de cada kilómetro"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={rows}
              layout="vertical"
              margin={{ top: 0, right: 64, bottom: 0, left: 0 }}
              barCategoryGap={3}
            >
              <CartesianGrid horizontal={false} stroke="var(--border)" />
              <XAxis
                type="number"
                hide
                domain={[(min: number) => min * 0.85, "dataMax"]}
              />
              <YAxis
                type="category"
                dataKey="label"
                width={28}
                tick={axisTick}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                cursor={{ fill: "var(--muted)" }}
                contentStyle={tooltipStyle}
                labelFormatter={(_, p) => `Km ${p?.[0]?.payload?.km ?? ""}`}
                formatter={(_v, _n, item) => {
                  const r = item.payload as (typeof rows)[number];
                  return [
                    `${formatDuration(r.pace_s_km)} /km${r.avg_hr ? ` · ${r.avg_hr} ppm` : ""} · +${r.elevation_gain_m} m`,
                    "Ritmo",
                  ];
                }}
              />
              <Bar
                dataKey="speed"
                radius={[0, 4, 4, 0]}
                isAnimationActive={false}
              >
                {rows.map((r) => (
                  <Cell
                    key={r.km}
                    fill={
                      r.pace_s_km === best
                        ? "var(--chart-1)"
                        : "color-mix(in oklab, var(--chart-1) 45%, var(--card))"
                    }
                  />
                ))}
                <LabelList
                  dataKey="pace_s_km"
                  position="right"
                  formatter={(v: number) => `${formatDuration(v)}`}
                  style={{ fontSize: 11, fill: "var(--foreground)" }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </figure>
        <details className="text-sm">
          <summary className="min-h-11 cursor-pointer content-center font-medium md:min-h-8">
            Tabla de parciales
          </summary>
          <table className="mt-1 w-full tabular-nums">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="py-1 font-normal">Km</th>
                <th className="py-1 font-normal">Ritmo</th>
                <th className="py-1 font-normal">FC</th>
                <th className="py-1 font-normal">Desnivel</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.km} className="border-t">
                  <td className="py-1">{r.label}</td>
                  <td className="py-1">{formatDuration(r.pace_s_km)} /km</td>
                  <td className="py-1">{r.avg_hr ? `${r.avg_hr} ppm` : "—"}</td>
                  <td className="py-1">+{r.elevation_gain_m} m</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.some((r) => r.distance_m < 990) && (
            <p className="mt-1 text-xs text-muted-foreground">
              * Último tramo, de menos de 1 km.
            </p>
          )}
        </details>
      </CardContent>
    </Card>
  );
}

/** Zonas de FC y VO2max (bajo el mapa) y parciales por km de la actividad. */
export function ActivityAnalysisCards({ activityId }: { activityId: number }) {
  const { data, isPending } = useActivityAnalysis(activityId);
  if (isPending)
    return (
      <div className="grid gap-4 md:gap-6 lg:grid-cols-2">
        <Skeleton className="h-72" />
        <Skeleton className="h-72" />
      </div>
    );
  if (!data) return null;
  const hasZones = data.hr_zones.zones.some((z) => z.seconds > 0);
  return (
    <>
      <div className="grid gap-4 md:gap-6 lg:grid-cols-2">
        {hasZones && <HrZonesCard data={data.hr_zones} />}
        <Vo2maxCard data={data.vo2max} />
      </div>
      {data.splits.length > 1 && <SplitsCard data={data} />}
    </>
  );
}
