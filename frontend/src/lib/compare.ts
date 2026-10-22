import { formatDuration, formatNumber } from "@/lib/format";

/** Ritmos por encima de esto (s/km) son paradas o andar: no se dibujan. */
export const MAX_PACE_S_KM = 900;

export const clipPace = (v: number | null) =>
  v != null && v > 0 && v <= MAX_PACE_S_KM ? v : null;

/** «1:23 más rápida» / «0:45 más lenta» / «igual» para la diferencia b − a en segundos. */
export function gapText(seconds: number | null): string {
  if (seconds == null) return "—";
  if (Math.abs(seconds) < 1) return "igual";
  return `${formatDuration(Math.abs(seconds))} ${seconds < 0 ? "más rápida" : "más lenta"}`;
}

/** Diferencia con signo para tablas: «−12 s», «+1:05». */
export function signedGap(seconds: number | null): string {
  if (seconds == null) return "—";
  const abs = Math.abs(seconds);
  const text = abs < 60 ? `${formatNumber(abs)} s` : formatDuration(abs);
  if (abs < 0.5) return "0 s";
  return `${seconds < 0 ? "−" : "+"}${text}`;
}

/** Ritmo en s/km → «5:12». */
export const paceText = (s: number | null) =>
  s == null ? "—" : formatDuration(s);

/** Eje X de distancia: «2,5 km». */
export const kmTick = (m: number) =>
  `${formatNumber(m / 1000, m % 1000 ? 1 : 0)} km`;
