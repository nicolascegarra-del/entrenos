"use client";

import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import { formatClock, hourTicks, type ClockPoint } from "@/lib/oura";

const axisTick = { fontSize: 11, fill: "var(--muted-foreground)" };
const tooltipStyle = {
  background: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
  color: "var(--popover-foreground)",
};

/** Marcas cada hora (o cada 3 h en rangos largos, para que no se pisen en el móvil). */
function ticksFor(min: number, max: number): number[] {
  const hours = (max - min) / 3_600_000;
  return hourTicks(min, max, hours > 14 ? 3 : hours > 8 ? 2 : 1);
}

/**
 * Curva intradía con eje X en horas y un solo eje Y (FC o HRV de la noche, MET del día).
 * Los huecos (null) cortan la línea en lugar de inventar valores.
 */
export function ClockLineChart({
  points,
  label,
  unit,
  color,
  format = (v) => String(Math.round(v)),
  height = "h-44",
}: {
  points: ClockPoint[];
  label: string;
  unit: string;
  color: string;
  format?: (v: number) => string;
  height?: string;
}) {
  const times = points.map((p) => p.t);
  const [min, max] = [Math.min(...times), Math.max(...times)];
  return (
    <div className={height}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={points}
          margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
        >
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={[min, max]}
            ticks={ticksFor(min, max)}
            tickFormatter={formatClock}
            tick={axisTick}
            stroke="var(--border)"
            tickLine={false}
          />
          <YAxis
            width={40}
            domain={["auto", "auto"]}
            tickFormatter={format}
            tick={axisTick}
            axisLine={false}
            tickLine={false}
            tickCount={4}
          />
          <Tooltip
            cursor={{ stroke: "var(--muted-foreground)", strokeWidth: 1 }}
            contentStyle={tooltipStyle}
            labelFormatter={(t: number) => formatClock(t)}
            formatter={(v: number) => [`${format(v)} ${unit}`, label]}
          />
          <Line
            dataKey="value"
            name={label}
            type="monotone"
            stroke={color}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, stroke: "var(--card)", strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export interface ScatterGroup {
  key: string;
  label: string;
  color: string;
  points: { t: number; bpm: number }[];
}

/** FC continua del día: un punto por minuto, coloreado por su origen, con leyenda. */
export function HeartRateDayChart({
  groups,
  height = "h-56",
}: {
  groups: ScatterGroup[];
  height?: string;
}) {
  const visible = groups.filter((g) => g.points.length);
  const times = visible.flatMap((g) => g.points.map((p) => p.t));
  const [min, max] = [Math.min(...times), Math.max(...times)];
  return (
    <div className={height}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis
            dataKey="t"
            name="Hora"
            type="number"
            scale="time"
            domain={[min, max]}
            ticks={ticksFor(min, max)}
            tickFormatter={formatClock}
            tick={axisTick}
            stroke="var(--border)"
            tickLine={false}
          />
          <YAxis
            dataKey="bpm"
            name="FC"
            width={40}
            domain={["auto", "auto"]}
            tick={axisTick}
            axisLine={false}
            tickLine={false}
            tickCount={4}
          />
          <ZAxis range={[14, 14]} />
          <Tooltip
            cursor={{ stroke: "var(--muted-foreground)", strokeWidth: 1 }}
            contentStyle={tooltipStyle}
            formatter={(v: number, name: string) =>
              name === "Hora" ? [formatClock(v), "Hora"] : [`${v} ppm`, "FC"]
            }
          />
          {visible.length > 1 && (
            <Legend
              verticalAlign="top"
              height={28}
              iconType="circle"
              wrapperStyle={{ fontSize: 12, color: "var(--foreground)" }}
            />
          )}
          {visible.map((g) => (
            <Scatter
              key={g.key}
              name={g.label}
              data={g.points}
              fill={g.color}
              isAnimationActive={false}
            />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
