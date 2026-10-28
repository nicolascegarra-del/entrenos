"use client";

import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatDate } from "@/lib/format";
import type { DeviceSpan } from "@/types/api";

export interface ChartSeries {
  key: string;
  label: string;
  color: string;
  kind: "line" | "area" | "bar" | "dots";
  /** Barras con el mismo `stack` se apilan (ej. minutos por zona de intensidad). */
  stack?: string;
}

interface TimeChartProps {
  data: Record<string, number | null>[];
  series: ChartSeries[];
  /** Formato de los valores del eje Y y del tooltip. */
  format: (v: number) => string;
  unit?: string;
  devices?: DeviceSpan[];
  height?: string;
  zeroLine?: boolean;
  /** Etiqueta del eje X: fecha corta (por defecto) o semana. */
  xLabel?: (t: number) => string;
  /** Franja de referencia horizontal (ej. zona segura del ACWR 0,8–1,3). */
  band?: { from: number; to: number; label: string };
  /** Línea horizontal de referencia (ej. tiempo objetivo). */
  refLine?: { y: number; label: string };
  /** Eje Y invertido (ritmos: más rápido = más arriba). */
  reversed?: boolean;
  /** Escala Y fija (small multiples: la misma en todos para poder compararlos). */
  yDomain?: [number, number];
}

const shortDate = (t: number) =>
  new Date(t).toLocaleDateString("es-ES", { day: "numeric", month: "short" });

/**
 * Gráfica temporal con eje X en fechas reales y un único eje Y.
 * Marca con una línea vertical cada cambio de reloj, porque las métricas
 * estimadas (VO2max, eficiencia…) pueden saltar al cambiar de dispositivo.
 */
export function TimeChart({
  data,
  series,
  format,
  unit = "",
  devices = [],
  height = "h-48",
  zeroLine,
  xLabel = shortDate,
  band,
  refLine,
  reversed,
  yDomain,
}: TimeChartProps) {
  const times = data.map((d) => d.t as number);
  const [min, max] = [Math.min(...times), Math.max(...times)];
  const changes = devices.slice(1).filter((d) => {
    const t = new Date(d.first_seen).getTime();
    return t >= min && t <= max;
  });

  return (
    <div className={height}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={data}
          margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
        >
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={xLabel}
            tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
            stroke="var(--border)"
            tickLine={false}
            minTickGap={40}
            padding={
              series.some((s) => s.kind === "bar")
                ? { left: 12, right: 12 }
                : undefined
            }
          />
          <YAxis
            width={44}
            reversed={reversed}
            domain={yDomain ?? ["auto", "auto"]}
            tickFormatter={format}
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
            labelFormatter={(t: number) =>
              formatDate(new Date(t).toISOString())
            }
            formatter={(v: number, name: string) => [
              `${format(v)}${unit ? ` ${unit}` : ""}`,
              name,
            ]}
          />
          {series.length > 1 && (
            <Legend
              verticalAlign="top"
              height={24}
              iconType="plainline"
              wrapperStyle={{ fontSize: 12, color: "var(--foreground)" }}
            />
          )}
          {band && (
            <ReferenceArea
              y1={band.from}
              y2={band.to}
              fill="var(--chart-3)"
              fillOpacity={0.12}
              ifOverflow="extendDomain"
              label={{
                value: band.label,
                position: "insideTopLeft",
                fontSize: 10,
                fill: "var(--muted-foreground)",
              }}
            />
          )}
          {refLine && (
            <ReferenceLine
              y={refLine.y}
              stroke="var(--foreground)"
              strokeDasharray="6 4"
              ifOverflow="extendDomain"
              label={{
                value: refLine.label,
                position: "insideBottomRight",
                fontSize: 11,
                fill: "var(--foreground)",
              }}
            />
          )}
          {zeroLine && (
            <ReferenceLine
              y={0}
              stroke="var(--muted-foreground)"
              strokeOpacity={0.6}
            />
          )}
          {changes.map((d) => (
            <ReferenceLine
              key={d.id}
              x={new Date(d.first_seen).getTime()}
              stroke="var(--muted-foreground)"
              strokeDasharray="4 4"
              label={{
                value: d.name,
                position: "insideTopRight",
                fontSize: 10,
                fill: "var(--muted-foreground)",
              }}
            />
          ))}
          {series.map((s) => {
            const common = {
              dataKey: s.key,
              name: s.label,
              isAnimationActive: false,
            };
            if (s.kind === "bar")
              return (
                <Bar
                  key={s.key}
                  {...common}
                  fill={s.color}
                  stackId={s.stack}
                  radius={s.stack ? undefined : [4, 4, 0, 0]}
                  maxBarSize={18}
                />
              );
            if (s.kind === "dots")
              return (
                <Scatter
                  key={s.key}
                  {...common}
                  fill={s.color}
                  shape="circle"
                />
              );
            if (s.kind === "area")
              return (
                <Area
                  key={s.key}
                  {...common}
                  type="monotone"
                  stroke={s.color}
                  strokeWidth={2}
                  fill={s.color}
                  fillOpacity={0.12}
                  dot={false}
                  connectNulls
                />
              );
            return (
              <Line
                key={s.key}
                {...common}
                type="monotone"
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: "var(--card)", strokeWidth: 2 }}
                connectNulls
              />
            );
          })}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Media móvil de las últimas `window` muestras (suaviza series ruidosas como la eficiencia). */
export function rollingMean(
  values: number[],
  window: number,
): (number | null)[] {
  return values.map((_, i) => {
    const slice = values.slice(Math.max(0, i - window + 1), i + 1);
    return slice.length >= Math.min(window, 3)
      ? slice.reduce((a, b) => a + b, 0) / slice.length
      : null;
  });
}
