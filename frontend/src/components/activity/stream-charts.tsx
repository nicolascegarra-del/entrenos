"use client";

import { useMemo } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatDuration, formatNumber, speedToPace } from "@/lib/format";
import type { Streams } from "@/types/api";

interface ChartSpec {
  channel: string;
  label: string;
  unit: string;
  color: string;
  /** Transforma el valor bruto (ej. m/s → s/km). */
  transform?: (v: number) => number | null;
  format: (v: number) => string;
  /** Ritmo: menos es mejor, el eje se invierte para que "más rápido" quede arriba. */
  reversed?: boolean;
}

/** Color fijo por métrica (sigue a la entidad, no al orden): ver --chart-* en globals.css. */
function chartSpecs(pace: boolean): ChartSpec[] {
  return [
    pace
      ? {
          channel: "speed",
          label: "Ritmo",
          unit: "/km",
          color: "var(--chart-1)",
          transform: (v) => speedToPace(v),
          format: (v) => formatDuration(v),
          reversed: true,
        }
      : {
          channel: "speed",
          label: "Velocidad",
          unit: "km/h",
          color: "var(--chart-1)",
          transform: (v) => v * 3.6,
          format: (v) => formatNumber(v, 1),
        },
    { channel: "hr", label: "Frecuencia cardiaca", unit: "ppm", color: "var(--chart-2)", format: (v) => formatNumber(v) },
    { channel: "power", label: "Potencia", unit: "W", color: "var(--chart-4)", format: (v) => formatNumber(v) },
    { channel: "altitude", label: "Altitud", unit: "m", color: "var(--chart-3)", format: (v) => formatNumber(v) },
    { channel: "cadence", label: "Cadencia", unit: "ppm", color: "var(--chart-4)", format: (v) => formatNumber(v) },
  ];
}

export function chartChannels(available: string[]): string[] {
  const wanted = ["time", "distance", "speed", "hr", "power", "altitude", "cadence"];
  return wanted.filter((c) => available.includes(c));
}

/** Percentiles 2–98 para que picos sueltos (GPS, pausas) no aplasten la gráfica. */
function robustDomain(values: number[]): [number, number] {
  const sorted = [...values].sort((a, b) => a - b);
  const lo = sorted[Math.floor(sorted.length * 0.02)];
  const hi = sorted[Math.ceil(sorted.length * 0.98) - 1];
  const pad = (hi - lo) * 0.08 || 1;
  return [lo - pad, hi + pad];
}

interface Props {
  streams: Streams;
  pace: boolean;
}

/** Gráficas pequeñas apiladas, una por métrica y con el eje X común (nunca doble eje Y). */
export function StreamCharts({ streams, pace }: Props) {
  const { channels } = streams;
  const byDistance = !!channels.distance?.some((v) => v);

  const rows = useMemo(() => {
    const xs = byDistance ? channels.distance : channels.time;
    return (xs ?? []).map((x, i) => {
      const row: Record<string, number | null> = { x: x == null ? null : byDistance ? x / 1000 : x };
      for (const spec of chartSpecs(pace)) {
        const raw = channels[spec.channel]?.[i];
        row[spec.channel] = raw == null ? null : spec.transform ? spec.transform(raw) : raw;
      }
      return row;
    });
  }, [channels, byDistance, pace]);

  const specs = chartSpecs(pace).filter((s) => rows.some((r) => r[s.channel] != null && r[s.channel] !== 0));
  if (!specs.length) return null;

  const xFormat = (v: number) => (byDistance ? `${formatNumber(v, 1)} km` : formatDuration(v));

  return (
    <div className="space-y-4">
      {specs.map((spec) => {
        const values = rows.map((r) => r[spec.channel]).filter((v): v is number => v != null && v !== 0);
        const avg = values.reduce((a, b) => a + b, 0) / values.length;
        return (
          <figure key={spec.channel} className="space-y-1">
            <figcaption className="flex items-baseline justify-between text-sm">
              <span className="font-medium text-foreground">{spec.label}</span>
              <span className="text-muted-foreground tabular-nums">
                media {spec.format(avg)} {spec.unit}
              </span>
            </figcaption>
            <div className="h-32 md:h-36">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={rows} syncId="activity" margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="0" />
                  <XAxis
                    dataKey="x"
                    type="number"
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={xFormat}
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    stroke="var(--border)"
                    tickLine={false}
                    minTickGap={40}
                  />
                  <YAxis
                    width={44}
                    domain={robustDomain(values)}
                    allowDataOverflow
                    reversed={spec.reversed}
                    tickFormatter={(v: number) => spec.format(v)}
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    axisLine={false}
                    tickLine={false}
                    tickCount={4}
                  />
                  <Tooltip
                    cursor={{ stroke: "var(--muted-foreground)", strokeWidth: 1 }}
                    contentStyle={{
                      background: "var(--popover)",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      fontSize: 12,
                      color: "var(--popover-foreground)",
                    }}
                    labelFormatter={(v: number) => xFormat(v)}
                    formatter={(v: number) => [`${spec.format(v)} ${spec.unit}`, spec.label]}
                  />
                  <Area
                    type="monotone"
                    dataKey={spec.channel}
                    stroke={spec.color}
                    strokeWidth={2}
                    fill={spec.color}
                    fillOpacity={0.12}
                    baseValue={spec.reversed ? "dataMax" : "dataMin"}
                    connectNulls
                    dot={false}
                    activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--card)" }}
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </figure>
        );
      })}
    </div>
  );
}
