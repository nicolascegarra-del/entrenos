import type {
  Gear,
  GarminStatus,
  InjuryReport,
  RaceGoal,
  SourcesStatus,
} from "@/types/api";

import { otherWatch } from "./watch-brands";

export interface Notice {
  key: string;
  status: "watch" | "alert" | "info";
  title: string;
  message: string;
  href: string;
}

export interface SetupStep {
  key: string;
  label: string;
  href: string;
}

/**
 * Avisos de Hoy, de más a menos urgente: conexión con Garmin caducada y riesgo de lesión.
 * Se juntan en una sola tarjeta en lugar de banners sueltos.
 */
export function buildNotices({
  garmin,
  injury,
}: {
  garmin?: GarminStatus;
  injury?: InjuryReport;
}): Notice[] {
  const out: Notice[] = [];
  if (garmin?.connection.status === "expired")
    out.push({
      key: "garmin",
      status: "alert",
      title: "Garmin desconectado",
      message:
        "La conexión ha caducado: vuelve a conectarla para seguir sincronizando.",
      href: "/ajustes/conexiones",
    });
  if (injury && injury.status !== "good") {
    const worst = injury.checks.filter((c) => c.status === injury.status);
    out.push({
      key: "injury",
      status: injury.status,
      title: worst.map((c) => c.title).join(" · ") || injury.summary,
      message: worst[0]?.message ?? "",
      href: "/progresion/salud#lesiones",
    });
  }
  return out;
}

/** Lo que falta por configurar para sacarle partido a la app (tarjeta «Completa tu configuración»). */
export function setupSteps({
  garmin,
  goals,
  gear,
  sources,
}: {
  sources?: SourcesStatus;
  garmin?: GarminStatus;
  goals?: RaceGoal[];
  gear?: Gear[];
}): SetupStep[] {
  const steps: SetupStep[] = [];
  if (
    garmin &&
    garmin.connection.status === "none" &&
    sources &&
    !otherWatch(sources)
  )
    steps.push({
      key: "watch",
      label: "Conecta tu reloj",
      href: "/ajustes/conexiones",
    });
  if (goals && !goals.some((g) => g.days_left >= 0 && g.result_time_s == null))
    steps.push({
      key: "goal",
      label: "Añade tu próxima carrera",
      href: "/objetivos/nuevo",
    });
  if (gear && !gear.some((g) => !g.retired))
    steps.push({
      key: "gear",
      label: "Registra tus zapatillas",
      href: "/material",
    });
  return steps;
}
