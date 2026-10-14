import { Bike, Dumbbell, Footprints, Waves, Activity as Generic, type LucideIcon } from "lucide-react";

const LOCALE = "es-ES";

/**
 * Formatea segundos como h:mm:ss (o m:ss si dura menos de una hora).
 * @param seconds - Duración en segundos.
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = h ? String(m).padStart(2, "0") : String(m);
  return `${h ? `${h}:` : ""}${mm}:${String(s).padStart(2, "0")}`;
}

/** Metros → "6,01 km" (o "850 m" por debajo de 1 km). */
export function formatDistance(meters: number | null | undefined): string {
  if (meters == null) return "—";
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toLocaleString(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} km`;
}

/** Velocidad m/s → segundos por km (null si está parado). */
export function speedToPace(speed: number | null | undefined): number | null {
  return speed && speed > 0.5 ? 1000 / speed : null;
}

/** Velocidad m/s → "4:15 /km". */
export function formatPace(speed: number | null | undefined): string {
  const pace = speedToPace(speed);
  return pace == null ? "—" : `${formatDuration(pace)} /km`;
}

/** Velocidad m/s → "28,4 km/h". */
export function formatSpeedKmh(speed: number | null | undefined): string {
  if (!speed) return "—";
  return `${(speed * 3.6).toLocaleString(LOCALE, { maximumFractionDigits: 1 })} km/h`;
}

/** Fecha ISO → "14/10/2026" (formato Klyp DD/MM/YYYY, hora local del navegador). */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(LOCALE, { day: "2-digit", month: "2-digit", year: "numeric" });
}

/** Fecha ISO → "mar 14/10/2026 · 17:58". */
export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  const weekday = d.toLocaleDateString(LOCALE, { weekday: "short" });
  const time = d.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" });
  return `${weekday} ${formatDate(iso)} · ${time}`;
}

export function formatNumber(value: number | null | undefined, decimals = 0): string {
  if (value == null) return "—";
  return value.toLocaleString(LOCALE, { maximumFractionDigits: decimals, minimumFractionDigits: decimals });
}

const SPORTS: Record<string, { label: string; icon: LucideIcon; pace: boolean }> = {
  running: { label: "Carrera", icon: Footprints, pace: true },
  trail_running: { label: "Trail", icon: Footprints, pace: true },
  treadmill_running: { label: "Cinta", icon: Footprints, pace: true },
  cycling: { label: "Ciclismo", icon: Bike, pace: false },
  road_biking: { label: "Carretera", icon: Bike, pace: false },
  mountain_biking: { label: "MTB", icon: Bike, pace: false },
  indoor_cycling: { label: "Rodillo", icon: Bike, pace: false },
  strength_training: { label: "Fuerza", icon: Dumbbell, pace: false },
  lap_swimming: { label: "Natación", icon: Waves, pace: false },
};

/** Etiqueta, icono y si el deporte se mide en ritmo (min/km) o velocidad. */
export function sportInfo(sport: string): { label: string; icon: LucideIcon; pace: boolean } {
  return SPORTS[sport] ?? { label: sport.replaceAll("_", " "), icon: Generic, pace: false };
}
