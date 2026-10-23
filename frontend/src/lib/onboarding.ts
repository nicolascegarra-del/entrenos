/** Pasos de la configuración guiada (/bienvenida), en orden. */
export const ONBOARDING_STEPS = [
  { key: "bienvenida", label: "Bienvenida" },
  { key: "reloj", label: "Tu reloj" },
  { key: "perfil", label: "Perfil" },
  { key: "ia", label: "Asistente IA" },
  { key: "listo", label: "Listo" },
] as const;

export type OnboardingStep = (typeof ONBOARDING_STEPS)[number]["key"];

/**
 * Índice del paso a partir del parámetro `?paso=` (para no perder el sitio al recargar).
 * @returns 0 si el parámetro falta o no es válido.
 */
export function stepIndex(param: string | null): number {
  const key = param === "garmin" ? "reloj" : param; // enlaces antiguos
  const i = ONBOARDING_STEPS.findIndex((s) => s.key === key);
  return i < 0 ? 0 : i;
}

/** Decide si hay que llevar al usuario a la configuración guiada. */
export function needsOnboarding(
  me: { onboarded: boolean } | undefined,
  pathname: string,
): boolean {
  return !!me && !me.onboarded && pathname !== "/bienvenida";
}
