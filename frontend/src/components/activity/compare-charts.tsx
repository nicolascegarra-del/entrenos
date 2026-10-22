"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { clipPace, kmTick, paceText, signedGap } from "@/lib/compare";
import { formatNumber } from "@/lib/format";
import type { ComparePoint } from "@/types/api";

const tooltipStyle = {
  background: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
  color: "var(--popover-foreground)",
};

function DistanceChart({
  data,
  title,
  children,
  format,
  reversed,
  zero,
}: {
  data: Record<string, number | null>[];
  title: string;
  children: React.ReactNode;
  format: (v: number) => string;
  reversed?: boolean;
  zero?: boolean;
}) {
  return (
    <figure>
      <figcaption className="mb-1 text-sm font-medium">{title}</figcaption>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data}
            margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
          >
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="distance_m"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickFormatter={kmTick}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              stroke="var(--border)"
              tickLine={false}
              minTickGap={40}
            />
            <YAxis
              width={44}
              reversed={reversed}
              domain={["auto", "auto"]}
              tickFormatter={format}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              axisLine={false}
              tickLine={false}
              tickCount={4}
            />
            {zero && <ReferenceLine y={0} stroke="var(--muted-foreground)" />}
            <Tooltip
              cursor={{ stroke: "var(--muted-foreground)", strokeWidth: 1 }}
              contentStyle={tooltipStyle}
              labelFormatter={(m: number) => kmTick(m)}
              formatter={(v: number, name: string) => [format(v), name]}
            />
            {children}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

/**
 * Gráficas del comparador alineadas por distancia: diferencia acumulada, ritmo y FC.
 * A siempre en --chart-1 y B en --chart-2 (mismo color que en el mapa).
 */
export function CompareCharts({
  points,
  labelA,
  labelB,
}: {
  points: ComparePoint[];
  labelA: string;
  labelB: string;
}) {
  const data = points.map((p) => ({
    distance_m: p.distance_m,
    gap_s: p.gap_s,
    pace_a: clipPace(p.pace_a),
    pace_b: clipPace(p.pace_b),
    hr_a: p.hr_a,
    hr_b: p.hr_b,
  }));
  const hasHr = points.some((p) => p.hr_a != null && p.hr_b != null);
  const legend = <Legend wrapperStyle={{ fontSize: 12 }} />;
  return (
    <div className="space-y-6">
      <DistanceChart
        data={data}
        title={`Diferencia acumulada (${labelB} frente a ${labelA}; por debajo de 0 = va por delante)`}
        format={(v) => signedGap(v)}
        zero
      >
        <Area
          dataKey="gap_s"
          name="Diferencia"
          type="monotone"
          stroke="var(--chart-2)"
          fill="var(--chart-2)"
          fillOpacity={0.15}
          strokeWidth={2}
          dot={false}
          connectNulls
        />
      </DistanceChart>
      <DistanceChart
        data={data}
        title="Ritmo (min/km)"
        format={(v) => paceText(v)}
        reversed
      >
        {legend}
        <Line
          dataKey="pace_a"
          name={labelA}
          type="monotone"
          stroke="var(--chart-1)"
          strokeWidth={2}
          dot={false}
          connectNulls
        />
        <Line
          dataKey="pace_b"
          name={labelB}
          type="monotone"
          stroke="var(--chart-2)"
          strokeWidth={2}
          dot={false}
          connectNulls
        />
      </DistanceChart>
      {hasHr && (
        <DistanceChart
          data={data}
          title="Frecuencia cardiaca (ppm)"
          format={(v) => formatNumber(v)}
        >
          {legend}
          <Line
            dataKey="hr_a"
            name={labelA}
            type="monotone"
            stroke="var(--chart-1)"
            strokeWidth={2}
            dot={false}
            connectNulls
          />
          <Line
            dataKey="hr_b"
            name={labelB}
            type="monotone"
            stroke="var(--chart-2)"
            strokeWidth={2}
            dot={false}
            connectNulls
          />
        </DistanceChart>
      )}
    </div>
  );
}
