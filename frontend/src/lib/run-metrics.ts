import type { ActivityAnalysis } from "@/types/api";

type Efficiency = NonNullable<ActivityAnalysis["efficiency"]>;
type Condition = NonNullable<ActivityAnalysis["performance_condition"]>;

const signed = (v: number) =>
  `${v > 0 ? "+" : ""}${v.toLocaleString("es-ES", { maximumFractionDigits: 1 })}`;

/** «+4 % más eficiente que tu media de 60 días (6 carreras)». */
export function efficiencyText(e: Efficiency): string {
  if (e.delta_pct == null)
    return "Aún no hay suficientes carreras en los últimos 60 días para compararla (hacen falta 3).";
  const runs = `tu media de 60 días (${e.baseline_runs} carreras)`;
  if (Math.abs(e.delta_pct) < 1) return `Igual que ${runs}.`;
  return e.delta_pct > 0
    ? `${signed(e.delta_pct)} % más eficiente que ${runs}.`
    : `${signed(e.delta_pct)} % menos eficiente que ${runs}: cansancio, calor, cuestas o un mal día.`;
}

/** Lectura de la condición de rendimiento (−20 a +20). */
export function conditionText(c: Condition): string {
  const v = c.initial;
  const base =
    v >= 5
      ? "Muy buen día: rindes por encima de tu nivel."
      : v >= 1
        ? "Buen día: algo por encima de tu nivel."
        : v > -3
          ? "Día normal, en tu nivel."
          : v > -6
            ? "Algo por debajo de tu nivel: puede ser fatiga."
            : "Bastante por debajo de tu nivel: descansa o baja la intensidad.";
  if (c.final != null && c.final - c.initial <= -5)
    return `${base} Fue bajando durante la carrera (fatiga acumulada).`;
  return base;
}

/** Intensidad frente al umbral (IF): <0,75 suave, <0,85 moderada, ~1 umbral. */
export function intensityText(intensity: number | null): string {
  if (intensity == null) return "Sin FC para calcularla";
  if (intensity < 0.75) return "Suave";
  if (intensity < 0.85) return "Moderada";
  if (intensity < 0.95) return "Alta (tempo)";
  if (intensity <= 1.05) return "En umbral";
  return "Por encima del umbral";
}
