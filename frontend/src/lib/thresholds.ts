import { formatDuration } from "@/lib/format";

export type ThresholdSource =
  "garmin" | "vdot" | "velocidad_critica" | "mejor_hora";

/** Nombre corto de cada estimación del ritmo umbral. */
export const THRESHOLD_LABEL: Record<ThresholdSource, string> = {
  garmin: "Garmin",
  vdot: "Daniels (tu nivel de carrera)",
  velocidad_critica: "Velocidad crítica",
  mejor_hora: "Tu mejor hora",
};

/** Alternativas del ritmo umbral de la más rápida a la más lenta, marcando la elegida. */
export function thresholdAlternatives(
  candidates: Partial<Record<ThresholdSource, number>> | undefined,
  chosen: ThresholdSource | null | undefined,
): { key: ThresholdSource; label: string; pace: string; chosen: boolean }[] {
  return Object.entries(candidates ?? {})
    .filter((e): e is [ThresholdSource, number] => typeof e[1] === "number")
    .sort((a, b) => a[1] - b[1])
    .map(([key, pace]) => ({
      key,
      label: THRESHOLD_LABEL[key] ?? key,
      pace: `${formatDuration(pace)} /km`,
      chosen: key === chosen,
    }));
}
