import type {
  CoachSettings,
  DevicesStatus,
  Gear,
  GarminStatus,
  InjuryReport,
  Profile,
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
  /** Por qué conviene (línea pequeña bajo el paso). */
  hint?: string;
}

/**
 * Avisos de Hoy, de más a menos urgente: conexión caducada (Garmin, Suunto, Amazfit, Xiaomi) y riesgo
 * de lesión. Se juntan en una sola tarjeta en lugar de banners sueltos.
 */
export function buildNotices({
  garmin,
  injury,
  devices,
}: {
  garmin?: GarminStatus;
  injury?: InjuryReport;
  devices?: DevicesStatus;
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
  for (const c of devices?.connections ?? [])
    if (c.status === "expired")
      out.push({
        key: c.provider,
        status: "alert",
        title: `${c.label} desconectado`,
        message:
          "La conexión ha caducado: vuelve a conectarla para seguir sincronizando.",
        href: `/ajustes/conexiones#reloj-${c.provider}`,
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

/** Datos del perfil que usa la app para calcular (edad, sexo, peso, altura) y que faltan. */
export function missingProfile(profile?: Profile): string[] {
  if (!profile) return [];
  const fields: [keyof Profile, string][] = [
    ["birth_date", "fecha de nacimiento"],
    ["sex", "sexo"],
    ["weight_kg", "peso"],
    ["height_cm", "altura"],
  ];
  return fields.filter(([k]) => profile[k] == null).map(([, label]) => label);
}

/**
 * Lo que falta por configurar para sacarle partido a la app (tarjeta «Completa tu configuración»).
 * Primero el reloj: con sus datos la entrevista propone lo detectado (FC máx., umbral, perfil) y solo pregunta
 * lo que falta. Sin IA (o con el módulo del entrenador IA apagado), el perfil y los umbrales se rellenan a mano.
 */
export function setupSteps({
  garmin,
  goals,
  gear,
  sources,
  devices,
  profile,
  coach,
  hasAi: hasAiInput,
  hasActivities,
  iaModule = true,
}: {
  sources?: SourcesStatus;
  devices?: DevicesStatus;
  garmin?: GarminStatus;
  goals?: RaceGoal[];
  gear?: Gear[];
  profile?: Profile;
  coach?: CoachSettings;
  /** undefined = aún cargando. */
  hasAi?: boolean;
  hasActivities?: boolean;
  /** Módulo «Entrenador IA» activo (lo decide el administrador). Apagado = como si no hubiera IA. */
  iaModule?: boolean;
}): SetupStep[] {
  const hasAi = iaModule ? hasAiInput : false;
  const steps: SetupStep[] = [];
  const noWatch =
    !!garmin &&
    garmin.connection.status === "none" &&
    !!sources &&
    !otherWatch(sources, devices);
  if (noWatch)
    steps.push({
      key: "watch",
      label: "Conecta tu reloj",
      hint: hasAi
        ? "Primero el reloj: con tus entrenos tu entrenador te propone tus datos reales."
        : undefined,
      href: "/ajustes/conexiones",
    });
  const syncing = garmin?.last_run?.status === "running";
  if (hasAi && coach && !coach.interview_done)
    steps.push({
      key: "interview",
      label: "Haz la entrevista inicial con tu entrenador (5 min)",
      hint: syncing
        ? "Espera a que termine la sincronización: así te propone tus datos reales."
        : hasActivities
          ? "Revisa los datos que ha sacado de tus entrenos y completa lo que falte (edad, peso, umbrales…)."
          : noWatch
            ? "Mejor después de conectar el reloj: así te propone tus datos reales."
            : "Te pregunta lo que falta (edad, peso, umbrales, historial…) y lo guarda en tu ficha.",
      href: "/asistente?modo=entrevista",
    });
  else if (hasAi === false && profile) {
    const missing = missingProfile(profile);
    if (missing.length)
      steps.push({
        key: "profile",
        label: "Completa tu perfil",
        hint: `Falta: ${missing.join(", ")}. Se usa para tu FC máx., calorías y comparativas.`,
        href: "/ajustes/perfil",
      });
    if (profile.hr_max_source !== "real")
      steps.push({
        key: "thresholds",
        label: "Revisa tu FC máxima y tus umbrales",
        hint:
          profile.hr_max_source === "tanaka"
            ? "Ahora se estiman por tu edad. Si los conoces de un test o tu reloj, mételos: afinan zonas y carga."
            : "Aún no hay datos. Si los conoces de un test o tu reloj, mételos: afinan zonas y carga.",
        href: "/progresion/rendimiento",
      });
  }
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
