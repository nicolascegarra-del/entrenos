/**
 * Lógica pura de la parte social (Amigos): formato de valores por métrica, textos de la clasificación,
 * marcador y ganador de los duelos, validación del @ y fechas relativas. Sin React para poder probarla.
 */

import {
  formatDate,
  formatDistance,
  formatDuration,
  formatNumber,
} from "./format";
import type {
  Duel,
  DuelDuration,
  DuelMetric,
  FeedItem,
  FollowStatus,
  LeaderboardMetric,
  SocialSport,
} from "@/types/api";

const LOCALE = "es-ES";

// ─── @handle ─────────────────────────────────────────────────────────────────

export const HANDLE_MIN = 3;
export const HANDLE_MAX = 30;
const HANDLE_RE = /^[a-z0-9_.]+$/;

/** Lo que escribe la persona → @ limpio: sin «@», sin espacios y en minúsculas. */
export function normalizeHandle(raw: string): string {
  return raw.trim().replace(/^@+/, "").toLowerCase();
}

/** Error del @ para el formulario, o null si vale. */
export function handleError(handle: string): string | null {
  if (handle.length < HANDLE_MIN)
    return `Tu @ necesita al menos ${HANDLE_MIN} caracteres.`;
  if (handle.length > HANDLE_MAX)
    return `Tu @ puede tener como mucho ${HANDLE_MAX} caracteres.`;
  if (!HANDLE_RE.test(handle))
    return "Solo letras minúsculas sin tilde, números, «_» y «.».";
  return null;
}

/** Propuesta de @ a partir del nombre visible: «Ana Pérez» → «ana.perez». */
export function suggestHandle(name: string): string {
  const base = name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, ".")
    .replace(/[^a-z0-9_.]/g, "")
    .replace(/\.{2,}/g, ".")
    .replace(/^\.+|\.+$/g, "")
    .slice(0, HANDLE_MAX);
  return base;
}

/** Iniciales para el avatar: «Ana Pérez» → «AP»; «ana» → «A». */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  const first = parts[0][0];
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return `${first}${last}`.toUpperCase();
}

/** Enlace público del perfil, para copiar o compartir. */
export const profileUrl = (origin: string, handle: string) =>
  `${origin.replace(/\/$/, "")}/u/${handle}`;

// ─── Métricas ────────────────────────────────────────────────────────────────

export const METRIC_LABELS: Record<DuelMetric, string> = {
  km: "Km",
  time: "Tiempo",
  elevation: "Desnivel",
  days: "Días",
  best_5k: "Mejor 5K",
  best_10k: "Mejor 10K",
};

export const SPORT_LABELS: Record<SocialSport, string> = {
  all: "Todo",
  running: "Carrera",
  cycling: "Bici",
};

export const DURATION_LABELS: Record<DuelDuration, string> = {
  "1w": "1 semana",
  "2w": "2 semanas",
  "1m": "1 mes",
};

/** ¿En esta métrica gana el valor más bajo? (las mejores marcas son tiempos). */
export const lowerWins = (metric: DuelMetric) =>
  metric === "best_5k" || metric === "best_10k";

/** Segundos → «3 h 05 min» o «45 min». */
function hoursMinutes(seconds: number): string {
  const total = Math.round(seconds / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (!h) return `${m} min`;
  return `${h} h ${String(m).padStart(2, "0")} min`;
}

/**
 * Valor de una métrica con su unidad: km en km, tiempo en segundos, desnivel en metros,
 * días en días y mejores marcas en segundos (m:ss).
 */
export function formatMetric(
  metric: DuelMetric,
  value: number | null | undefined,
): string {
  if (value == null) return "—";
  switch (metric) {
    case "km":
      return `${formatNumber(value, 1)} km`;
    case "time":
      return hoursMinutes(value);
    case "elevation":
      return `${formatNumber(value)} m`;
    case "days": {
      const n = Math.round(value);
      return `${n} ${n === 1 ? "día" : "días"}`;
    }
    case "best_5k":
    case "best_10k":
      return formatDuration(value);
  }
}

/** «Te faltan 3,2 km para pasar a Ana» (null si vas primero o no hay datos). */
export function gapText(
  metric: LeaderboardMetric,
  gap: number | null | undefined,
  name: string | null | undefined,
): string | null {
  if (gap == null || !name) return null;
  if (gap <= 0) return `Estás empatado con ${name}: un empujón y lo pasas.`;
  return `Te faltan ${formatMetric(metric, gap)} para pasar a ${name}`;
}

/** Puesto en texto: 1 → «1.º». */
export const ordinal = (rank: number) => `${rank}.º`;

export interface RankChange {
  dir: "up" | "down" | "same" | "new";
  /** Puestos que sube o baja (0 si igual o nuevo). */
  steps: number;
  /** Texto corto visible: «↑2», «↓1», «=» o «Nuevo». */
  short: string;
  /** Texto para lectores de pantalla. */
  label: string;
}

/** Cambio de posición frente al periodo anterior (menor puesto = mejor). */
export function rankChange(rank: number, prev: number | null): RankChange {
  if (prev == null)
    return {
      dir: "new",
      steps: 0,
      short: "Nuevo",
      label: "Nuevo en la clasificación",
    };
  const steps = Math.abs(prev - rank);
  const puestos = steps === 1 ? "puesto" : "puestos";
  if (rank < prev)
    return {
      dir: "up",
      steps,
      short: `↑${steps}`,
      label: `Sube ${steps} ${puestos}`,
    };
  if (rank > prev)
    return {
      dir: "down",
      steps,
      short: `↓${steps}`,
      label: `Baja ${steps} ${puestos}`,
    };
  return { dir: "same", steps: 0, short: "=", label: "Mismo puesto" };
}

// ─── Duelos ──────────────────────────────────────────────────────────────────

/** La otra persona del duelo (el rival). */
export const rivalOf = (duel: Duel) =>
  duel.i_am_challenger ? duel.opponent : duel.challenger;

/** Tu user_id dentro del duelo. */
export const myIdIn = (duel: Duel) =>
  duel.i_am_challenger ? duel.challenger.user_id : duel.opponent.user_id;

/** Quién va ganando: «me», «them» o «tie» (sin valores, empate). */
export function duelLeader(duel: Duel): "me" | "them" | "tie" {
  const lower = lowerWins(duel.metric);
  const mine = duel.my_value;
  const theirs = duel.their_value;
  // En mejores marcas, no tener marca es ir detrás; en el resto, contar como 0.
  if (lower) {
    if (mine == null && theirs == null) return "tie";
    if (mine == null) return "them";
    if (theirs == null) return "me";
    return mine < theirs ? "me" : mine > theirs ? "them" : "tie";
  }
  const a = mine ?? 0;
  const b = theirs ?? 0;
  return a > b ? "me" : a < b ? "them" : "tie";
}

/**
 * Tu parte de la barra comparativa (0–1). En métricas «más es mejor» es tu valor sobre la suma;
 * en las mejores marcas (menos es mejor) se invierte para que la barra larga sea la del que gana.
 */
export function duelShare(duel: Duel): number {
  const mine = duel.my_value;
  const theirs = duel.their_value;
  if (lowerWins(duel.metric)) {
    if (mine == null && theirs == null) return 0.5;
    if (mine == null) return 0;
    if (theirs == null) return 1;
    const total = mine + theirs;
    return total > 0 ? theirs / total : 0.5;
  }
  const a = Math.max(0, mine ?? 0);
  const b = Math.max(0, theirs ?? 0);
  return a + b > 0 ? a / (a + b) : 0.5;
}

/** Marcador en una línea: «Tú 23,4 km · Ana 21,0 km». */
export function duelScore(duel: Duel): string {
  const rival = rivalOf(duel).display_name.split(" ")[0];
  return `Tú ${formatMetric(duel.metric, duel.my_value)} · ${rival} ${formatMetric(duel.metric, duel.their_value)}`;
}

/** Resultado de un duelo terminado (null si no ha terminado). */
export function duelOutcome(duel: Duel): "win" | "loss" | "draw" | null {
  if (duel.status !== "finished") return null;
  if (duel.winner_id == null) return "draw";
  return duel.winner_id === myIdIn(duel) ? "win" : "loss";
}

export const OUTCOME_LABELS = {
  win: "Victoria",
  loss: "Derrota",
  draw: "Empate",
} as const;

/** Balance del historial: victorias, derrotas y empates. */
export function duelRecord(duels: Duel[]) {
  const out = { wins: 0, losses: 0, draws: 0 };
  for (const d of duels) {
    const o = duelOutcome(d);
    if (o === "win") out.wins++;
    else if (o === "loss") out.losses++;
    else if (o === "draw") out.draws++;
  }
  return out;
}

/** «3 victorias · 1 derrota · 0 empates». */
export function recordText(r: { wins: number; losses: number; draws: number }) {
  const n = (k: number, one: string, many: string) =>
    `${k} ${k === 1 ? one : many}`;
  return [
    n(r.wins, "victoria", "victorias"),
    n(r.losses, "derrota", "derrotas"),
    n(r.draws, "empate", "empates"),
  ].join(" · ");
}

/** Día ISO (YYYY-MM-DD) → número de día UTC, para restar fechas sin líos de horario. */
const dayNumber = (iso: string) => {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return Date.UTC(y, m - 1, d) / 86_400_000;
};

/** Hoy en formato YYYY-MM-DD (hora local). */
export function todayIso(now: Date = new Date()): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** Días que quedan contando hoy (el último día del duelo cuenta). 0 = terminado. */
export function daysLeft(endDate: string, today: string): number {
  return Math.max(0, dayNumber(endDate) - dayNumber(today) + 1);
}

/** «Quedan 5 días», «Último día» o «Terminado». */
export function daysLeftText(days: number): string {
  if (days <= 0) return "Terminado";
  if (days === 1) return "Último día";
  return `Quedan ${days} días`;
}

/** Descripción corta del reto: «Km · Carrera · 1 semana» (sin duración si no se sabe). */
export function duelDescription(duel: Duel): string {
  const sport =
    duel.sport === "all" ? "Todos los deportes" : SPORT_LABELS[duel.sport];
  return `${METRIC_LABELS[duel.metric]} · ${sport} · del ${formatDate(duel.start_date)} al ${formatDate(duel.end_date)}`;
}

// ─── Feed ────────────────────────────────────────────────────────────────────

/** «ahora», «hace 5 min», «hace 3 h», «ayer», «hace 4 días» o la fecha si pasó más de una semana. */
export function relativeDate(iso: string, now: Date = new Date()): string {
  const diff = (now.getTime() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "ahora";
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
  if (diff < 86_400) return `hace ${Math.floor(diff / 3600)} h`;
  const days = Math.round(
    dayNumber(todayIso(now)) - dayNumber(todayIso(new Date(iso))),
  );
  if (days <= 1) return "ayer";
  if (days < 7) return `hace ${days} días`;
  return formatDate(iso);
}

const PACE_SPORTS = new Set(["running", "trail_running", "treadmill_running"]);

export interface FeedStat {
  label: string;
  value: string;
}

/** Cifras de una tarjeta del feed: distancia, tiempo, ritmo (carrera) o velocidad (bici) y desnivel. */
export function feedStats(item: FeedItem): FeedStat[] {
  const out: FeedStat[] = [];
  if (item.distance_m)
    out.push({ label: "Distancia", value: formatDistance(item.distance_m) });
  out.push({
    label: "Tiempo",
    value: formatDuration(item.moving_duration_s ?? item.duration_s),
  });
  if (item.avg_speed && item.avg_speed > 0) {
    if (PACE_SPORTS.has(item.sport)) {
      if (item.avg_speed > 0.5)
        out.push({
          label: "Ritmo",
          value: `${formatDuration(1000 / item.avg_speed)} /km`,
        });
    } else
      out.push({
        label: "Velocidad",
        value: `${(item.avg_speed * 3.6).toLocaleString(LOCALE, { maximumFractionDigits: 1 })} km/h`,
      });
  }
  if (item.elevation_gain_m != null && item.elevation_gain_m > 0)
    out.push({
      label: "Desnivel",
      value: `${formatNumber(item.elevation_gain_m)} m`,
    });
  return out;
}

/** Texto del botón de seguir según el estado. */
export function followLabel(status: FollowStatus): string {
  return status === "accepted"
    ? "Siguiendo"
    : status === "pending"
      ? "Pendiente"
      : "Seguir";
}

/** Páginas del feed en caché (useInfiniteQuery). */
export interface FeedPages {
  pages: { items: FeedItem[]; next_before: string | null }[];
  pageParams: unknown[];
}

/** Cambia una actividad en todas las páginas del feed (para kudos optimistas, visibilidad…). */
export function patchFeed(
  data: FeedPages | undefined,
  activityId: number,
  patch: (item: FeedItem) => Partial<FeedItem>,
): FeedPages | undefined {
  if (!data) return data;
  return {
    ...data,
    pages: data.pages.map((p) => ({
      ...p,
      items: p.items.map((i) =>
        i.activity_id === activityId ? { ...i, ...patch(i) } : i,
      ),
    })),
  };
}

/** Kudos tras tocar 👏: alterna el tuyo y ajusta el contador (actualización optimista). */
export const toggledKudos = (
  item: Pick<FeedItem, "kudos_count" | "kudoed_by_me">,
) => ({
  kudoed_by_me: !item.kudoed_by_me,
  kudos_count: Math.max(0, item.kudos_count + (item.kudoed_by_me ? -1 : 1)),
});

export const COMMENT_MAX = 500;

/** Opciones de la zona oculta del mapa (metros alrededor del inicio y el final). */
export const HIDE_MAP_OPTIONS = [0, 200, 300, 500, 1000];

export const hideMapLabel = (m: number) =>
  m === 0 ? "No ocultar" : m >= 1000 ? "1 km" : `${m} m`;
