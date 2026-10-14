"use client";

import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatTargetValue, metricInfo } from "@/lib/plan";
import type { ComplianceStep, StepStatus, TargetMetric } from "@/types/api";

const STATUS_FILL: Record<StepStatus, string> = {
  ok: "#0e9f6e",
  near: "#d97706",
  off: "#dc2626",
};

interface DotProps {
  cx?: number;
  cy?: number;
  payload?: { step: ComplianceStep };
}

/** Punto de 10 px con anillo del color de la superficie para separarlo de la banda. */
function StatusDot({ cx, cy, payload }: DotProps) {
  if (cx == null || cy == null || !payload) return null;
  const status = payload.step.status;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={5}
      fill={status ? STATUS_FILL[status] : "var(--chart-5)"}
      stroke="var(--card)"
      strokeWidth={2}
    />
  );
}

/**
 * Valor real de cada repetición frente a la banda objetivo: un punto por serie,
 * una sola métrica y un solo eje. En ritmo el eje se invierte (más rápido arriba).
 * El estado del punto también aparece como texto en la tabla de pasos.
 */
export function RepsChart({
  steps,
  metric,
}: {
  steps: ComplianceStep[];
  metric: TargetMetric;
}) {
  const data = steps.map((s) => ({
    name: s.label.replace("Serie ", "#"),
    value: s.actual.value,
    step: s,
  }));
  const values = data.map((d) => d.value).filter((v): v is number => v != null);
  const lo = Math.min(...steps.map((s) => s.planned.target_min ?? Infinity));
  const hi = Math.max(...steps.map((s) => s.planned.target_max ?? -Infinity));
  const all = [...values, ...[lo, hi].filter(Number.isFinite)];
  const pad = (Math.max(...all) - Math.min(...all)) * 0.2 || 5;
  const domain: [number, number] = [
    Math.max(0, Math.min(...all) - pad),
    Math.max(...all) + pad,
  ];
  const { unit, label } = metricInfo(metric);

  return (
    <figure className="space-y-1">
      <figcaption className="text-sm font-medium">
        {label} por serie{" "}
        <span className="font-normal text-muted-foreground">
          · franja verde = objetivo
        </span>
      </figcaption>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data}
            margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
          >
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              tickLine={false}
              stroke="var(--border)"
              padding={{ left: 12, right: 12 }}
            />
            <YAxis
              width={44}
              domain={domain}
              reversed={metric === "pace"}
              allowDataOverflow
              tickFormatter={(v: number) => formatTargetValue(metric, v)}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              axisLine={false}
              tickLine={false}
              tickCount={4}
            />
            {Number.isFinite(lo) && Number.isFinite(hi) && (
              <ReferenceArea
                y1={lo}
                y2={hi}
                fill="var(--chart-3)"
                fillOpacity={0.15}
                stroke="var(--chart-3)"
                strokeOpacity={0.5}
                ifOverflow="extendDomain"
              />
            )}
            <Tooltip
              cursor={{ stroke: "var(--muted-foreground)", strokeWidth: 1 }}
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 12,
                color: "var(--popover-foreground)",
              }}
              formatter={(v: number) => [
                `${formatTargetValue(metric, v)} ${unit}`,
                label,
              ]}
            />
            {/* Línea fina que une las series + puntos con el estado de cada una. */}
            <Line
              dataKey="value"
              stroke="var(--muted-foreground)"
              strokeOpacity={0.4}
              strokeWidth={1}
              dot={<StatusDot />}
              activeDot={{ r: 7, stroke: "var(--card)", strokeWidth: 2 }}
              isAnimationActive={false}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
