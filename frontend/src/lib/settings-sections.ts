import type {
  AiProviders,
  DevicesStatus,
  GarminStatus,
  Me,
  NotificationConfig,
  OuraStatus,
  SourcesStatus,
} from "@/types/api";

import { connectedDevices } from "./watch-brands";

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
  sources,
  oura,
  devices,
}: {
  sources?: SourcesStatus;
  oura?: OuraStatus;
  devices?: DevicesStatus;
  garmin?: GarminStatus;
  ai?: AiProviders;
  notifications?: NotificationConfig;
  me?: Me;
}): Partial<Record<SettingsKey, SettingsStatus>> {
  const out: Partial<Record<SettingsKey, SettingsStatus>> = {};
  if (garmin) {
    // Todo lo conectado, no solo Garmin: con un Oura y sin Garmin no se avisa de «Garmin desconectado».
    const all = connectedDevices({ garmin, sources, oura, devices });
    out.conexiones = all.broken.length
      ? {
          text: `${all.broken.join(" y ")}: conexión caducada, vuelve a conectarla`,
          warn: true,
        }
      : { text: all.label, warn: all.connected.length === 0 };
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
