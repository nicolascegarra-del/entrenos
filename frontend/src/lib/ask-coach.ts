/**
 * Preguntas preparadas para el entrenador IA desde cada pantalla. Llevan los datos clave (y los ids), así el
 * entrenador consulta el detalle con sus herramientas sin que tengas que escribir nada.
 */
import { formatDate } from "@/lib/format";
import type { ActivitySummary, Summary } from "@/types/api";

/** Enlace al chat que envía la pregunta nada más abrirlo (en una conversación nueva). */
export const askCoachHref = (question: string) =>
  `/asistente?q=${encodeURIComponent(question)}&auto=1`;

export function askAboutActivity(
  a: Pick<ActivitySummary, "id" | "name" | "start_time">,
): string {
  return (
    `Analiza mi entreno «${a.name || "sin nombre"}» del ${formatDate(a.start_time)} (id ${a.id}): ` +
    "ritmo, pulso, zonas, vueltas y sensaciones. ¿Qué tal fue y qué me recomiendas?"
  );
}

export function askAboutSession(s: {
  id: number;
  day: string;
  title: string;
}): string {
  return (
    `Sobre mi sesión planificada «${s.title}» del ${formatDate(`${s.day}T12:00:00`)} (id ${s.id}): ` +
    "¿cómo la hago, a qué ritmos o pulsos, y encaja con cómo llego?"
  );
}

export function askAboutProgress(period: string): string {
  return (
    `Explícame cómo ha ido mi forma en los últimos ${period}: carga, frescura, ` +
    "ritmos y salud. ¿Qué está mejorando, qué no y qué me recomiendas?"
  );
}

/** Preguntas sugeridas en Hoy según tu día (2 o 3, la más útil primero). */
export function todaySuggestions(
  summary: Pick<Summary, "planned_this_week" | "readiness">,
  today: string,
): string[] {
  const out: string[] = [];
  const session = summary.planned_this_week.find(
    (p) => p.day === today && p.activity_id == null,
  );
  if (
    summary.readiness.status === "alert" ||
    summary.readiness.status === "watch"
  )
    out.push("¿Entreno hoy o mejor descanso?");
  if (session) out.push(`¿Cómo hago hoy «${session.title}»?`);
  out.push("¿Qué tal voy esta semana?");
  if (out.length < 3) out.push("¿Qué me toca los próximos días?");
  return out.slice(0, 3);
}
