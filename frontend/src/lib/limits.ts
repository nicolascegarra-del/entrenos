import type { AccountLimits } from "@/types/api";

/**
 * Describe los límites de una cuenta en frases cortas para la interfaz.
 * @param limits - Límites de la cuenta (null = sin límite).
 * @returns Lista vacía si la cuenta no tiene límites.
 */
export function describeLimits(limits: AccountLimits): string[] {
  const out: string[] = [];
  if (limits.history_days != null)
    out.push(`últimos ${limits.history_days} días de Garmin`);
  if (limits.max_goals != null)
    out.push(
      `hasta ${limits.max_goals} ${limits.max_goals === 1 ? "objetivo activo" : "objetivos activos"}`,
    );
  if (limits.max_sessions_week != null)
    out.push(
      `hasta ${limits.max_sessions_week} ${limits.max_sessions_week === 1 ? "sesión" : "sesiones"} por semana`,
    );
  return out;
}
