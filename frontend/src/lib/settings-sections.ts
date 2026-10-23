import type {
  AiProviders,
  GarminStatus,
  Me,
  NotificationConfig,
} from "@/types/api";

export type SettingsKey =
  "perfil" | "conexiones" | "notificaciones" | "asistente" | "cuenta";

export interface SettingsStatus {
  text: string;
  /** Algo requiere atención (p. ej. Garmin caducado). */
  warn?: boolean;
}

/** Estado en una línea de cada sección de Ajustes, para verlo sin entrar. */
export function settingsStatus({
  garmin,
  ai,
  notifications,
  me,
}: {
  garmin?: GarminStatus;
  ai?: AiProviders;
  notifications?: NotificationConfig;
  me?: Me;
}): Partial<Record<SettingsKey, SettingsStatus>> {
  const out: Partial<Record<SettingsKey, SettingsStatus>> = {};
  if (garmin) {
    const s = garmin.connection.status;
    const name = garmin.connection.display_name;
    out.conexiones =
      s === "ok"
        ? { text: `Garmin conectado${name ? ` (${name})` : ""}` }
        : s === "expired"
          ? { text: "Garmin caducado: vuelve a conectarlo", warn: true }
          : { text: "Sin reloj conectado", warn: true };
  }
  if (ai) {
    const active = ai.providers.filter((p) => p.configured && p.enabled);
    const main = active.find((p) => p.is_default) ?? active[0];
    out.asistente = main
      ? {
          text: `${main.label.split(" (")[0]} · ${main.model ?? main.default_model}`,
        }
      : { text: "Sin configurar" };
  }
  if (notifications) {
    const n = notifications.devices.length;
    out.notificaciones = {
      text: n
        ? `Activadas en ${n} ${n === 1 ? "dispositivo" : "dispositivos"}`
        : "Desactivadas",
    };
  }
  if (me)
    out.cuenta = {
      text: `${me.email} · ${me.tier === "full" ? "Completa" : "Básica"}`,
    };
  return out;
}
