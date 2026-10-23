import { formatDuration } from "@/lib/format";
import type {
  PerformanceTest,
  TestProtocol,
  TestResults,
  TestSport,
} from "@/types/api";

const CYCLING = [
  "cycling",
  "road_biking",
  "mountain_biking",
  "indoor_cycling",
  "gravel_cycling",
  "virtual_ride",
  "cyclocross",
];

/** Familia de deporte de una actividad para elegir sus tests (null si no hay tests para ella). */
export function testSport(sport: string): TestSport | null {
  if (sport.includes("running")) return "running";
  if (CYCLING.includes(sport)) return "cycling";
  if (sport.includes("swimming")) return "swimming";
  return null;
}

/** Tests que se pueden detectar en una actividad de ese deporte. */
export function protocolsFor(
  protocols: TestProtocol[] | undefined,
  sport: string,
): TestProtocol[] {
  const family = testSport(sport);
  return (protocols ?? []).filter((p) => p.detectable && p.sport === family);
}

/** Valores del test listos para mostrar, en orden de importancia. */
export function testValues(
  r: TestResults,
): { key: string; label: string; value: string }[] {
  const out: { key: string; label: string; value: string }[] = [];
  if (r.threshold_pace_s_km)
    out.push({
      key: "pace",
      label: "Ritmo umbral",
      value: `${formatDuration(r.threshold_pace_s_km)} /km`,
    });
  if (r.lthr)
    out.push({ key: "lthr", label: "FC umbral", value: `${r.lthr} ppm` });
  if (r.vo2max)
    out.push({
      key: "vo2max",
      label: "VO2max",
      value: r.vo2max.toLocaleString("es-ES", { maximumFractionDigits: 1 }),
    });
  if (r.vdot)
    out.push({
      key: "vdot",
      label: "VDOT",
      value: r.vdot.toLocaleString("es-ES", { maximumFractionDigits: 1 }),
    });
  if (r.hr_max)
    out.push({ key: "hr_max", label: "FC máxima", value: `${r.hr_max} ppm` });
  if (r.time_s)
    out.push({ key: "time", label: "Tiempo", value: formatDuration(r.time_s) });
  if (r.distance_m)
    out.push({
      key: "distance",
      label: "Distancia",
      value: `${r.distance_m.toLocaleString("es-ES")} m`,
    });
  if (r.d_prime_m)
    out.push({
      key: "dprime",
      label: "Reserva anaeróbica (D′)",
      value: `${r.d_prime_m} m`,
    });
  return out;
}

export const CONFIDENCE_LABEL: Record<string, string> = {
  alta: "Confianza alta",
  media: "Confianza media",
  baja: "Confianza baja",
};

export const STATUS_LABEL: Record<PerformanceTest["status"], string> = {
  detected: "Pendiente de revisar",
  confirmed: "Aplicado a tus zonas",
  failed: "No se pudo calcular",
};

/** ¿Sigue mandando sobre Garmin y las estimaciones? (confirmado en las últimas 8 semanas) */
export function isActive(test: PerformanceTest, today = new Date()): boolean {
  if (test.status !== "confirmed") return false;
  const days =
    (today.getTime() - new Date(`${test.test_date}T00:00:00`).getTime()) /
    86_400_000;
  return days <= 56;
}

/** «m:ss» o «mm:ss» → segundos por km (vacío = null; NaN si no se entiende). */
export function parsePace(text: string): number | null {
  const value = text.trim();
  if (!value) return null;
  const m = /^(\d{1,2}):([0-5]\d)$/.exec(value);
  return m ? Number(m[1]) * 60 + Number(m[2]) : Number.NaN;
}
