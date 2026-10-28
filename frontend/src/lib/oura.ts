/**
 * Lógica pura de la conexión con el anillo Oura y de sus datos de salud (noche y día):
 * estado de la tarjeta de Ajustes, fuente de recuperación, hipnograma, FC por origen, perfil de
 * actividad, modo descanso y textos. Sin React, para poder probarla con payloads de ejemplo.
 */

import { addDays, toIsoDay } from "@/lib/plan";
import type {
  HealthDay,
  HealthNight,
  HeartRateSample,
  IntervalSeries,
  OuraRing,
  OuraStatus,
  RecoverySource,
  RestPeriod,
  SeriesPoint,
} from "@/types/api";

const LOCALE = "es-ES";

// ─── Tarjeta de Ajustes ─────────────────────────────────────────────────────

export type OuraCardState =
  "unconfigured" | "disconnected" | "expired" | "connected";

/**
 * Qué enseña la tarjeta de Oura. Sin credenciales del administrador no se puede conectar;
 * un token caducado pide volver a conectar aunque el backend lo marque como desconectado.
 */
export function ouraCardState(s: OuraStatus): OuraCardState {
  if (!s.configured) return "unconfigured";
  if (s.status === "expired") return "expired";
  if (s.connected) return "connected";
  return "disconnected";
}

/** El selector de fuente solo tiene sentido si hay reloj y anillo a la vez. */
export function showSourcePicker(s: OuraStatus | undefined): boolean {
  return !!s && s.connected && s.has_watch;
}

/** Umbral de batería baja del anillo (en %). */
export const LOW_BATTERY = 15;

export function lowBattery(ring: OuraRing | null | undefined): boolean {
  return ring?.battery_level != null && ring.battery_level < LOW_BATTERY;
}

/** Texto de la importación del histórico (null si no hay nada que contar). */
export function historyText(h: OuraStatus["history"]): string | null {
  const range =
    h.from && h.to
      ? ` del ${formatDayShort(h.from)} al ${formatDayShort(h.to)}`
      : h.from
        ? ` desde el ${formatDayShort(h.from)}`
        : "";
  if (h.status === "running")
    return `Importando tu histórico${range}… puede tardar unos minutos.`;
  if (h.status === "done") return `Histórico importado${range}.`;
  if (h.status === "error")
    return "No se pudo importar todo tu histórico. Prueba «Sincronizar ahora».";
  return null;
}

/** Descripción de la talla, el modelo y el color del anillo, sin huecos vacíos. */
export function ringSummary(ring: OuraRing | null | undefined): string | null {
  if (!ring) return null;
  const parts = [
    ring.model ? humanize(ring.model) : null,
    ring.size != null && ring.size !== "" ? `talla ${ring.size}` : null,
    ring.color ? humanize(ring.color) : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

export const RECOVERY_SOURCES: {
  key: RecoverySource;
  label: string;
  hint: string;
}[] = [
  {
    key: "auto",
    label: "Automático",
    hint: "Cada noche se usa el dato más completo: normalmente el del anillo, si lo llevabas puesto.",
  },
  {
    key: "watch",
    label: "Reloj",
    hint: "El sueño, la HRV y la FC en reposo salen siempre del reloj; Oura solo añade lo que el reloj no mide.",
  },
  {
    key: "oura",
    label: "Oura",
    hint: "El sueño, la HRV, la FC en reposo y la puntuación de recuperación salen siempre del anillo.",
  },
];

/**
 * ¿Los datos de recuperación de hoy vienen de Oura? Manda la elección del usuario; en automático,
 * lo que diga la noche (su `source`) o, sin reloj, el anillo.
 */
export function recoveryFromOura(
  s: OuraStatus | undefined,
  nightSource: string | null | undefined,
): boolean {
  if (!s?.connected) return false;
  if (s.recovery_source === "oura") return true;
  if (s.recovery_source === "watch") return false;
  if (nightSource) return nightSource === "oura";
  return !s.has_watch;
}

// ─── Tiempos y formatos ─────────────────────────────────────────────────────

/** Segundos → "7 h 32 min", "45 min" o "—". */
export function formatHm(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const total = Math.round(seconds / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (!h) return `${m} min`;
  return m ? `${h} h ${m} min` : `${h} h`;
}

/** Instante (ms) → "23:05" en la hora local del navegador. */
export function formatClock(ms: number): string {
  return new Date(ms).toLocaleTimeString(LOCALE, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** "2026-10-27" → "27 oct" (sin desfase de zona horaria). */
export function formatDayShort(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString(LOCALE, {
    day: "numeric",
    month: "short",
  });
}

/** "2026-10-27" → "Martes, 27 de octubre de 2026". */
export function formatDayLong(iso: string): string {
  const s = new Date(`${iso}T12:00:00`).toLocaleDateString(LOCALE, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Día ISO desplazado `n` días (navegación anterior/siguiente). */
export function shiftDay(iso: string, n: number): string {
  return toIsoDay(addDays(new Date(`${iso}T12:00:00`), n));
}

/** ¿Es un día ISO válido (para las rutas `/noche/[dia]` y `/dia/[dia]`)? */
export function isIsoDay(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const d = new Date(`${value}T12:00:00`);
  return !Number.isNaN(d.getTime()) && toIsoDay(d) === value;
}

/** Horas en punto entre dos instantes (marcas del eje de hora). */
export function hourTicks(startMs: number, endMs: number, step = 1): number[] {
  const first = new Date(startMs);
  first.setMinutes(0, 0, 0);
  if (first.getTime() < startMs) first.setHours(first.getHours() + 1);
  const out: number[] = [];
  for (
    let d = first;
    d.getTime() <= endMs;
    d = new Date(d.getTime() + step * 3_600_000)
  )
    out.push(d.getTime());
  return out;
}

/** Quita lo que no es texto legible de una clave de la API: "gen3_heritage" → "Gen3 heritage". */
export function humanize(key: string): string {
  const s = key.replace(/[_-]+/g, " ").trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : key;
}

// ─── Tramos (hipnograma y perfil de actividad) ──────────────────────────────

export interface Run {
  code: string;
  /** Instantes en ms. */
  start: number;
  end: number;
}

/** Une los caracteres seguidos iguales en tramos con su hora de inicio y de fin. */
export function decodeRuns(
  start: string,
  intervalS: number,
  chars: string,
): Run[] {
  const t0 = new Date(start).getTime();
  const step = intervalS * 1000;
  if (!Number.isFinite(t0) || step <= 0) return [];
  const runs: Run[] = [];
  for (let i = 0; i < chars.length; i++) {
    const code = chars[i];
    const last = runs[runs.length - 1];
    if (last && last.code === code) last.end += step;
    else runs.push({ code, start: t0 + i * step, end: t0 + (i + 1) * step });
  }
  return runs;
}

export type SleepPhase = "deep" | "light" | "rem" | "awake";

/** Fases del hipnograma, de arriba (despierto) a abajo (profundo). */
export const PHASES: {
  key: SleepPhase;
  code: string;
  label: string;
  /** Clase de Tailwind: un solo tono por profundidad y el despierto diferenciado. */
  className: string;
}[] = [
  {
    key: "awake",
    code: "4",
    label: "Despierto",
    className: "bg-sleep-awake",
  },
  {
    key: "rem",
    code: "3",
    label: "REM",
    className: "bg-sleep-rem",
  },
  {
    key: "light",
    code: "2",
    label: "Ligero",
    className: "bg-sleep-light",
  },
  {
    key: "deep",
    code: "1",
    label: "Profundo",
    className: "bg-sleep-deep",
  },
];

export interface PhaseRun {
  phase: SleepPhase;
  start: number;
  end: number;
}

export function hypnogramRuns(h: HealthNight["hypnogram"]): PhaseRun[] {
  if (!h) return [];
  const byCode = new Map(PHASES.map((p) => [p.code, p.key]));
  return decodeRuns(h.start, h.interval_s || 300, h.phases).flatMap((r) => {
    const phase = byCode.get(r.code);
    return phase ? [{ phase, start: r.start, end: r.end }] : [];
  });
}

/** Segundos en cada fase según el hipnograma. */
export function phaseTotals(runs: PhaseRun[]): Record<SleepPhase, number> {
  const out: Record<SleepPhase, number> = {
    deep: 0,
    light: 0,
    rem: 0,
    awake: 0,
  };
  for (const r of runs) out[r.phase] += (r.end - r.start) / 1000;
  return out;
}

/** Clases de actividad cada 5 minutos, de menos a más intensa. */
export const ACTIVITY_CLASSES: {
  code: string;
  label: string;
  className: string;
}[] = [
  {
    code: "0",
    label: "Sin llevarlo",
    className: "bg-muted",
  },
  {
    code: "1",
    label: "Descanso",
    className: "bg-activity-1",
  },
  {
    code: "2",
    label: "Inactivo",
    className: "bg-activity-2",
  },
  {
    code: "3",
    label: "Baja",
    className: "bg-activity-3",
  },
  {
    code: "4",
    label: "Media",
    className: "bg-activity-4",
  },
  {
    code: "5",
    label: "Alta",
    className: "bg-activity-5",
  },
];

export function activityRuns(
  c: NonNullable<HealthDay["activity"]>["class_5min"],
): Run[] {
  if (!c) return [];
  const known = new Set(ACTIVITY_CLASSES.map((a) => a.code));
  return decodeRuns(c.start, 300, c.classes).filter((r) => known.has(r.code));
}

// ─── Series ─────────────────────────────────────────────────────────────────

export interface ClockPoint {
  t: number;
  value: number | null;
}

/** Serie a intervalos → puntos con hora; los ceros y huecos quedan como null (corte de línea). */
export function seriesPoints(
  s:
    | IntervalSeries
    | { start: string; interval_s: number; items: number[] }
    | null
    | undefined,
): ClockPoint[] {
  if (!s) return [];
  const t0 = new Date(s.start).getTime();
  if (!Number.isFinite(t0)) return [];
  return s.items.map((v, i) => ({
    t: t0 + i * s.interval_s * 1000,
    value: v == null || !Number.isFinite(v) || v <= 0 ? null : v,
  }));
}

/** ¿Hay algún valor que pintar? */
export const hasValues = (points: ClockPoint[]) =>
  points.some((p) => p.value != null);

export type HrOrigin = "sleep" | "rest" | "awake" | "workout" | "session";

/** Orígenes de la FC del día, con su color categórico fijo (nunca de estado). */
export const HR_ORIGINS: { key: HrOrigin; label: string; color: string }[] = [
  { key: "sleep", label: "Sueño", color: "var(--chart-4)" },
  { key: "rest", label: "Reposo", color: "var(--chart-3)" },
  { key: "awake", label: "Despierto", color: "var(--chart-5)" },
  { key: "workout", label: "Entreno", color: "var(--chart-2)" },
  { key: "session", label: "Sesión", color: "var(--chart-1)" },
];

/** Origen de Oura → grupo de la gráfica («live» es una medición puntual: va con las sesiones). */
export function hrOrigin(source: string): HrOrigin {
  switch (source) {
    case "sleep":
      return "sleep";
    case "rest":
      return "rest";
    case "workout":
      return "workout";
    case "session":
    case "live":
      return "session";
    default:
      return "awake";
  }
}

export interface HrPoint {
  t: number;
  bpm: number;
}

/**
 * Agrupa la FC del día por origen y la reduce a una muestra por minuto (media), para que un
 * entreno con un dato por segundo no tape el resto ni haga lenta la gráfica.
 */
export function heartRateByOrigin(
  samples: HeartRateSample[],
  bucketS = 60,
): Record<HrOrigin, HrPoint[]> {
  const acc = new Map<
    string,
    { origin: HrOrigin; t: number; sum: number; n: number }
  >();
  for (const [epoch, bpm, source] of samples) {
    if (!Number.isFinite(epoch) || !Number.isFinite(bpm) || bpm <= 0) continue;
    const origin = hrOrigin(source);
    const bucket = Math.floor(epoch / bucketS) * bucketS;
    const key = `${origin}:${bucket}`;
    const cur = acc.get(key);
    if (cur) {
      cur.sum += bpm;
      cur.n += 1;
    } else acc.set(key, { origin, t: bucket * 1000, sum: bpm, n: 1 });
  }
  const out: Record<HrOrigin, HrPoint[]> = {
    sleep: [],
    rest: [],
    awake: [],
    workout: [],
    session: [],
  };
  for (const v of acc.values())
    out[v.origin].push({ t: v.t, bpm: Math.round(v.sum / v.n) });
  for (const k of Object.keys(out) as HrOrigin[])
    out[k].sort((a, b) => a.t - b.t);
  return out;
}

/**
 * Une varias series diarias por día (para un gráfico con varias líneas del mismo eje).
 * Los días que faltan en una serie quedan como null.
 */
export function mergeByDay(
  series: Record<string, SeriesPoint[] | undefined>,
  transform: (v: number) => number = (v) => v,
): ({ day: string } & Record<string, number | null | string>)[] {
  const days = new Map<string, Record<string, number | null>>();
  const keys = Object.keys(series);
  for (const key of keys)
    for (const p of series[key] ?? []) {
      const row =
        days.get(p.day) ?? Object.fromEntries(keys.map((k) => [k, null]));
      row[key] = transform(p.value);
      days.set(p.day, row);
    }
  return [...days.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, row]) => ({ day, ...row }));
}

// ─── Modo descanso ──────────────────────────────────────────────────────────

/** ¿Cae `day` dentro de algún periodo de modo descanso? (sin fin = sigue activo). */
export function restPeriodOn(
  periods: RestPeriod[] | undefined,
  day: string,
): RestPeriod | null {
  return (
    periods?.find(
      (p) => p.start_date <= day && (p.end_date == null || day <= p.end_date),
    ) ?? null
  );
}

/** Días de la lista que están en modo descanso. */
export function restDays(
  periods: RestPeriod[] | undefined,
  days: string[],
): Set<string> {
  return new Set(days.filter((d) => restPeriodOn(periods, d)));
}

// ─── Contribuidores y textos ────────────────────────────────────────────────

export type ContributorKind = "readiness" | "sleep" | "activity" | "resilience";

/** Nombres llanos de los contribuidores de Oura, en el orden en que se muestran. */
export const CONTRIBUTORS: Record<ContributorKind, Record<string, string>> = {
  readiness: {
    previous_night: "Noche anterior",
    sleep_balance: "Equilibrio de sueño",
    sleep_regularity: "Regularidad del sueño",
    previous_day_activity: "Actividad del día anterior",
    activity_balance: "Equilibrio de actividad",
    resting_heart_rate: "FC en reposo",
    hrv_balance: "Equilibrio de HRV",
    recovery_index: "Índice de recuperación",
    body_temperature: "Temperatura corporal",
  },
  sleep: {
    total_sleep: "Sueño total",
    efficiency: "Eficiencia",
    restfulness: "Descanso sin interrupciones",
    rem_sleep: "Sueño REM",
    deep_sleep: "Sueño profundo",
    latency: "Latencia",
    timing: "Horario",
  },
  activity: {
    stay_active: "Mantenerse activo",
    move_every_hour: "Moverse cada hora",
    meet_daily_targets: "Cumplir el objetivo diario",
    training_frequency: "Frecuencia de entreno",
    training_volume: "Volumen de entreno",
    recovery_time: "Tiempo de recuperación",
  },
  resilience: {
    sleep_recovery: "Recuperación durante el sueño",
    daytime_recovery: "Recuperación durante el día",
    stress: "Estrés",
  },
};

export interface Contributor {
  key: string;
  label: string;
  value: number;
}

/** Contribuidores con valor, en el orden conocido y los desconocidos al final. */
export function contributorList(
  record: Record<string, number | null> | null | undefined,
  kind: ContributorKind,
): Contributor[] {
  if (!record) return [];
  const names = CONTRIBUTORS[kind];
  const order = Object.keys(names);
  return Object.entries(record)
    .filter((e): e is [string, number] => typeof e[1] === "number")
    .sort(([a], [b]) => {
      const ia = order.indexOf(a);
      const ib = order.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
    })
    .map(([key, value]) => ({
      key,
      label: names[key] ?? humanize(key),
      value: Math.max(0, Math.min(100, value)),
    }));
}

/** Niveles de resiliencia de Oura (la métrica diaria `resilience_level` va de 1 a 5). */
export const RESILIENCE_LEVELS: Record<string, string> = {
  limited: "Limitada",
  adequate: "Suficiente",
  solid: "Sólida",
  strong: "Fuerte",
  exceptional: "Excepcional",
};

export function resilienceLabel(level: string | null | undefined): string {
  if (!level) return "—";
  return RESILIENCE_LEVELS[level] ?? humanize(level);
}

/** 1–5 → nombre del nivel (eje de la serie diaria). */
export function resilienceLevelName(n: number): string {
  const names = Object.values(RESILIENCE_LEVELS);
  return names[Math.round(n) - 1] ?? String(n);
}

const STRESS_SUMMARY: Record<string, string> = {
  restored: "Día de recuperación",
  normal: "Día normal",
  stressful: "Día estresante",
};

export const stressSummaryLabel = (s: string | null | undefined) =>
  s ? (STRESS_SUMMARY[s] ?? humanize(s)) : null;

const SESSION_TYPES: Record<string, string> = {
  breathing: "Respiración",
  meditation: "Meditación",
  nap: "Siesta",
  relaxation: "Relajación",
  rest: "Descanso",
  body_status: "Estado del cuerpo",
};

export const sessionLabel = (type: string) =>
  SESSION_TYPES[type] ?? humanize(type);

const MOODS: Record<string, string> = {
  bad: "Mal",
  worse: "Peor",
  same: "Igual",
  good: "Bien",
  great: "Muy bien",
};

export const moodLabel = (m: string | null | undefined) =>
  m ? (MOODS[m] ?? humanize(m)) : null;

const SLEEP_RECOMMENDATIONS: Record<string, string> = {
  improve_efficiency: "Intenta dormir de forma más continua.",
  earlier_bedtime: "Prueba a acostarte antes.",
  later_bedtime: "Prueba a acostarte más tarde.",
  earlier_wake_up_time: "Prueba a levantarte antes.",
  later_wake_up_time: "Prueba a levantarte más tarde.",
  follow_optimal_bedtime: "Sigue tu horario ideal para acostarte.",
};

const SLEEP_TIME_STATUS: Record<string, string> = {
  not_enough_nights: "Aún faltan noches para calcular tu horario ideal.",
  not_enough_recent_nights:
    "Faltan noches recientes para calcular tu horario ideal.",
  bad_sleep_quality:
    "Tus últimas noches no han sido buenas: primero hay que mejorar el sueño.",
  only_recommended_found: "Horario recomendado según tus noches.",
  optimal_found: "Tu horario ideal para acostarte.",
};

/** Segundos desde la medianoche local (negativos = antes) → "23:30". */
export function offsetClock(offset: number): string {
  const s = (((Math.round(offset) % 86_400) + 86_400) % 86_400) / 60;
  const h = Math.floor(s / 60);
  const m = Math.round(s % 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** Texto del horario recomendado (null si Oura no da nada). */
export function sleepTimeText(st: HealthNight["sleep_time"]): {
  window: string | null;
  status: string | null;
  recommendation: string | null;
} | null {
  if (!st) return null;
  const window = st.optimal_bedtime
    ? `Entre las ${offsetClock(st.optimal_bedtime.start_offset)} y las ${offsetClock(st.optimal_bedtime.end_offset)}`
    : null;
  const status = st.status
    ? (SLEEP_TIME_STATUS[st.status] ?? humanize(st.status))
    : null;
  const recommendation = st.recommendation
    ? (SLEEP_RECOMMENDATIONS[st.recommendation] ?? humanize(st.recommendation))
    : null;
  return window || status || recommendation
    ? { window, status, recommendation }
    : null;
}

/** ¿Tiene la noche algo que enseñar? */
export function nightHasData(n: HealthNight | null | undefined): boolean {
  if (!n) return false;
  return (
    !!n.main ||
    n.naps.length > 0 ||
    !!n.hypnogram?.phases ||
    n.sleep_score != null ||
    n.readiness?.score != null ||
    n.spo2?.average != null
  );
}

/** ¿Tiene el día algo que enseñar? */
export function dayHasData(d: HealthDay | null | undefined): boolean {
  if (!d) return false;
  return (
    d.heartrate.length > 0 ||
    !!d.activity ||
    !!d.stress ||
    !!d.resilience ||
    d.sessions.length > 0 ||
    d.tags.length > 0 ||
    !!d.rest_mode
  );
}

/** Nombre llano del origen de los datos de la noche. */
export function sourceLabel(source: string | null | undefined): string | null {
  if (!source) return null;
  const names: Record<string, string> = {
    oura: "Oura",
    garmin: "Garmin",
    coros: "COROS",
    apple: "Apple Watch",
    health_connect: "Health Connect",
  };
  return names[source] ?? humanize(source);
}

/** "+0,3 °C" / "−0,2 °C". */
export function formatTempDelta(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v).toLocaleString(LOCALE, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 2,
  });
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${abs} °C`;
}
