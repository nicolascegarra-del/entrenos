"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatDuration, formatNumber } from "@/lib/format";
import type { TestResults } from "@/types/api";

const axisTick = { fontSize: 11, fill: "var(--muted-foreground)" };

/**
 * Curva de lactato del test escalonado: lactato por escalón (eje y) frente a la intensidad (ritmo o
 * vatios), con LT1, LT2 y la referencia de 4 mmol/L. Incluye la tabla de escalones para leerla sin gráfica.
 */
export function LactateChart({
  results,
  cycling,
}: {
  results: TestResults;
  cycling: boolean;
}) {
  const steps = results.lactate_steps ?? [];
  if (steps.length < 2) return null;
  // En carrera la intensidad llega en m/s: se enseña como ritmo (más rápido a la derecha).
  const label = (x: number) =>
    cycling ? `${Math.round(x)} W` : `${formatDuration(1000 / x)} /km`;
  const lt1 = cycling
    ? results.lt1_power
    : results.lt1_pace_s_km && 1000 / results.lt1_pace_s_km;
  const lt2 = cycling
    ? results.ftp
    : results.threshold_pace_s_km && 1000 / results.threshold_pace_s_km;
  return (
    <div className="space-y-2">
      <figure
        className="h-56"
        aria-label="Curva de lactato: lactato de cada escalón según la intensidad, con LT1 y LT2"
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={steps}
            margin={{ top: 16, right: 12, bottom: 0, left: 0 }}
          >
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="intensity"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickFormatter={label}
              tick={axisTick}
              stroke="var(--border)"
              tickLine={false}
              minTickGap={36}
            />
            <YAxis
              width={36}
              tickFormatter={(v: number) => formatNumber(v)}
              tick={axisTick}
              axisLine={false}
              tickLine={false}
              tickCount={4}
            />
            <ReferenceLine
              y={4}
              stroke="var(--muted-foreground)"
              strokeDasharray="4 4"
            />
            {lt1 ? (
              <ReferenceLine
                x={lt1}
                stroke="var(--chart-2)"
                strokeWidth={2}
                label={{
                  value: "LT1",
                  position: "top",
                  fontSize: 11,
                  fill: "var(--foreground)",
                }}
              />
            ) : null}
            {lt2 ? (
              <ReferenceLine
                x={lt2}
                stroke="var(--chart-1)"
                strokeWidth={2}
                label={{
                  value: "LT2",
                  position: "top",
                  fontSize: 11,
                  fill: "var(--foreground)",
                }}
              />
            ) : null}
            <Tooltip
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 12,
                color: "var(--popover-foreground)",
              }}
              labelFormatter={(x: number) => label(x)}
              formatter={(v: number) => [
                `${formatNumber(v, 1)} mmol/L`,
                "Lactato",
              ]}
            />
            <Line
              dataKey="lactate"
              type="monotone"
              stroke="var(--chart-3)"
              strokeWidth={2}
              dot={{ r: 4, strokeWidth: 2, fill: "var(--card)" }}
              activeDot={{ r: 6 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </figure>
      <details className="text-sm">
        <summary className="min-h-11 cursor-pointer content-center font-medium md:min-h-8">
          Escalones del test
        </summary>
        <table className="mt-1 w-full tabular-nums">
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th className="py-1 font-normal">
                {cycling ? "Potencia" : "Ritmo"}
              </th>
              <th className="py-1 font-normal">Lactato</th>
              <th className="py-1 font-normal">FC</th>
            </tr>
          </thead>
          <tbody>
            {steps.map((s) => (
              <tr key={s.intensity} className="border-t">
                <td className="py-1">{label(s.intensity)}</td>
                <td className="py-1">{formatNumber(s.lactate, 1)} mmol/L</td>
                <td className="py-1">
                  {s.hr ? `${Math.round(s.hr)} ppm` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
