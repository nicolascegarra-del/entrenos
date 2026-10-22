import type { PlanAdjustment, PlanPhase, SessionKind } from "@/types/api";

export const WEEKDAY_SHORT = ["L", "M", "X", "J", "V", "S", "D"];
export const WEEKDAY_LONG = [
  "lunes",
  "martes",
  "miércoles",
  "jueves",
  "viernes",
  "sábado",
  "domingo",
];

export const PHASE_HELP: Record<PlanPhase, string> = {
  base: "Construir resistencia aeróbica con rodajes suaves y algo de umbral.",
  build: "Subir el volumen y añadir calidad: umbral y series.",
  peak: "La carga más alta y específica: series y ritmo de carrera.",
  taper: "Bajar el volumen para llegar fresco a la carrera.",
};

export const KIND_LABEL: Record<SessionKind, string> = {
  easy: "Rodaje suave",
  long: "Tirada larga",
  threshold: "Umbral",
  intervals: "Series",
  race_pace: "Ritmo de carrera",
  race: "Carrera",
};

export const ACTION_LABEL: Record<PlanAdjustment["action"], string> = {
  progress: "Seguimos según lo previsto",
  hold: "Mantenemos el volumen",
  reduce: "Bajamos la carga",
};

/** Sesiones de calidad (el resto son suaves): sirve para mostrar el reparto ~80/20. */
export function isQuality(kind: SessionKind | null | undefined): boolean {
  return kind === "threshold" || kind === "intervals" || kind === "race_pace";
}

/**
 * Días de entrenamiento válidos para el plan: al menos 2, sin repetir y ordenados.
 * La tirada larga tiene que caer en uno de ellos.
 */
export function planDaysValid(weekdays: number[], longDay: number): boolean {
  const unique = new Set(weekdays);
  return unique.size >= 2 && unique.has(longDay);
}
