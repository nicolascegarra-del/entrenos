import {
  CircleAlert,
  CircleCheck,
  CircleX,
  type LucideIcon,
} from "lucide-react";

import { formatDistance, formatDuration, formatNumber } from "@/lib/format";
import type {
  BlockKind,
  PlannedBlock,
  StepStatus,
  TargetMetric,
} from "@/types/api";

export const BLOCK_KINDS: { value: BlockKind; label: string }[] = [
  { value: "warmup", label: "Calentamiento" },
  { value: "steady", label: "Continuo" },
  { value: "interval", label: "Series" },
  { value: "recovery", label: "Recuperación" },
  { value: "cooldown", label: "Vuelta a la calma" },
];

export const TARGET_METRICS: {
  value: TargetMetric;
  label: string;
  unit: string;
  clock: boolean;
}[] = [
  { value: "pace", label: "Ritmo", unit: "/km", clock: true },
  { value: "speed", label: "Velocidad", unit: "km/h", clock: false },
  { value: "hr", label: "Frecuencia cardiaca", unit: "ppm", clock: false },
  { value: "power", label: "Potencia", unit: "W", clock: false },
  { value: "cadence", label: "Cadencia", unit: "ppm", clock: false },
];

export function metricInfo(metric: TargetMetric) {
  return TARGET_METRICS.find((m) => m.value === metric) ?? TARGET_METRICS[0];
}

/**
 * Convierte "4:15" o "1:05:30" en segundos; un número suelto se toma como minutos.
 * @returns Segundos, o null si el texto no es válido.
 */
export function parseClock(text: string): number | null {
  const value = text.trim();
  if (!value) return null;
  if (!/^\d+(:\d{1,2}){0,2}$/.test(value)) return null;
  const parts = value.split(":").map(Number);
  if (parts.length === 1) return parts[0] * 60;
  if (parts.slice(1).some((p) => p >= 60)) return null;
  return parts.reduce((acc, p) => acc * 60 + p, 0);
}

/** Valor de objetivo legible: ritmo como m:ss, el resto como número. */
export function formatTargetValue(
  metric: TargetMetric,
  value: number | null,
): string {
  if (value == null) return "—";
  return metricInfo(metric).clock
    ? formatDuration(value)
    : formatNumber(value, metric === "speed" ? 1 : 0);
}

export function formatTarget(
  metric: TargetMetric | null,
  min: number | null,
  max: number | null,
): string {
  if (!metric) return "";
  const { unit } = metricInfo(metric);
  if (min != null && max != null)
    return `${formatTargetValue(metric, min)}–${formatTargetValue(metric, max)} ${unit}`;
  if (min != null) return `≥ ${formatTargetValue(metric, min)} ${unit}`;
  return `≤ ${formatTargetValue(metric, max)} ${unit}`;
}

function quantity(duration: number | null, distance: number | null): string {
  if (distance) return formatDistance(distance);
  if (duration) return formatDuration(duration);
  return "libre";
}

/** Resumen de un bloque: "6 × 200 m @ 3:10–3:40 /km · rec. 1:30". */
export function blockSummary(block: PlannedBlock): string {
  const base = quantity(block.duration_s, block.distance_m);
  const reps = block.repeat > 1 ? `${block.repeat} × ${base}` : base;
  const target = block.target_metric
    ? ` @ ${formatTarget(block.target_metric, block.target_min, block.target_max)}`
    : "";
  const recovery =
    block.repeat > 1 && (block.recovery_duration_s || block.recovery_distance_m)
      ? ` · rec. ${quantity(block.recovery_duration_s, block.recovery_distance_m)}`
      : "";
  return `${reps}${target}${recovery}`;
}

/** Colores de estado reservados (nunca para series): siempre con icono y texto. */
export const STATUS: Record<
  StepStatus,
  { label: string; icon: LucideIcon; className: string }
> = {
  ok: {
    label: "Cumplido",
    icon: CircleCheck,
    className:
      "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  },
  near: {
    label: "Cerca",
    icon: CircleAlert,
    className:
      "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300",
  },
  off: {
    label: "Fuera",
    icon: CircleX,
    className: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  },
};

export function scoreStatus(score: number | null): StepStatus | null {
  if (score == null) return null;
  return score >= 90 ? "ok" : score >= 70 ? "near" : "off";
}

export const DIRECTION_LABEL = {
  fast: "más rápido",
  slow: "más lento",
  low: "por debajo",
  high: "por encima",
} as const;

/** Lunes de la semana de `date` (semana europea). */
export function startOfWeek(date: Date): Date {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d;
}

export function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

/** Fecha local → "YYYY-MM-DD" (ISO, formato de la API). */
export function toIsoDay(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
