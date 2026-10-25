/**
 * Módulos de la app que el administrador activa o desactiva para todos (Admin → Módulos).
 * Desactivar solo oculta la interfaz (y su API responde 404): nunca borra datos.
 */

export type ModuleKey = "entrenadores" | "ia" | "reloj" | "rutas" | "nutricion";

export type Modules = Record<ModuleKey, boolean>;

/**
 * Mientras se cargan los módulos se muestra todo como estaba antes de existir este ajuste
 * (lo que ya existe, visible): así no parpadea al entrar.
 */
export const LOADING_MODULES: Modules = {
  entrenadores: false,
  ia: true,
  reloj: true,
  rutas: true,
  nutricion: false,
};

/** Qué explica cada interruptor del panel de administración. */
export const MODULE_INFO: { key: ModuleKey; label: string; hint: string }[] = [
  {
    key: "entrenadores",
    label: "Entrenadores",
    hint: "Entrenadores reales que siguen a sus atletas. Aún no está disponible: de momento solo es el interruptor.",
  },
  {
    key: "ia",
    label: "Entrenador IA",
    hint: "Oculta el chat, el análisis de actividades, la revisión semanal, la entrevista y el botón central del entrenador.",
  },
  {
    key: "reloj",
    label: "Envío al reloj",
    hint: "Oculta los botones para enviar sesiones a Garmin y COROS y para el envío automático.",
  },
  {
    key: "rutas",
    label: "Rutas",
    hint: "Oculta Plan → Rutas y las rutas asociadas a las sesiones.",
  },
  {
    key: "nutricion",
    label: "Nutrición",
    hint: "Aún no está disponible: de momento solo es el interruptor.",
  },
];

/** ¿Está activo? Sin módulo = siempre; sin datos (cargando o error) = como estaba. */
export function moduleOn(
  modules: Modules | undefined,
  key?: ModuleKey,
): boolean {
  if (!key) return true;
  return (modules ?? LOADING_MODULES)[key];
}

/** Quita los elementos cuyo módulo está apagado. */
export function filterByModule<T extends { module?: ModuleKey }>(
  items: T[],
  modules: Modules | undefined,
): T[] {
  return items.filter((i) => moduleOn(modules, i.module));
}

/** Rutas de la app que pertenecen a un módulo (para no enseñar una pantalla apagada). */
const PATH_MODULES: { base: string; module: ModuleKey }[] = [
  { base: "/asistente", module: "ia" },
  { base: "/ajustes/asistente", module: "ia" },
  { base: "/plan/rutas", module: "rutas" },
];

/** Módulo apagado al que pertenece `pathname` (o null si se puede ver). */
export function disabledModuleFor(
  pathname: string,
  modules: Modules | undefined,
): ModuleKey | null {
  const hit = PATH_MODULES.find(
    (p) => pathname === p.base || pathname.startsWith(`${p.base}/`),
  );
  return hit && !moduleOn(modules, hit.module) ? hit.module : null;
}

export const moduleLabel = (key: ModuleKey) =>
  MODULE_INFO.find((m) => m.key === key)?.label ?? key;
