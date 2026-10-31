/**
 * Módulos de la app que el administrador activa o desactiva: un valor general (Admin → Módulos)
 * y, si quiere, otro propio para cada cuenta (Admin → Usuarios → Módulos), que manda sobre el general.
 * Desactivar solo oculta la interfaz (y su API responde 404): nunca borra datos.
 */

export type ModuleKey =
  | "entrenadores"
  | "ia"
  | "reloj"
  | "rutas"
  | "nutricion"
  | "oura"
  | "suunto"
  | "zepp"
  | "xiaomi"
  | "samsung";

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
  oura: true,
  suunto: true,
  zepp: true,
  xiaomi: true,
  samsung: true,
};

/**
 * Qué explica cada interruptor del panel de administración. En esta rama no hay modo entrenador ni
 * nutrición: sus claves siguen en `Modules` (apagadas) pero no se ofrecen en el panel.
 */
export const MODULE_INFO: { key: ModuleKey; label: string; hint: string }[] = [
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
    key: "oura",
    label: "Oura Ring",
    hint: "Oculta la conexión con el anillo Oura.",
  },
  {
    key: "suunto",
    label: "Suunto",
    hint: "Oculta la conexión con la cuenta de Suunto (no oficial: apágalo si Suunto la rompe).",
  },
  {
    key: "zepp",
    label: "Amazfit (Zepp)",
    hint: "Oculta la conexión con la cuenta de Zepp para relojes Amazfit (no oficial).",
  },
  {
    key: "xiaomi",
    label: "Xiaomi (Mi Fitness)",
    hint: "Oculta la conexión por QR con la cuenta de Xiaomi para Smart Band y Redmi Watch (no oficial, beta).",
  },
  {
    key: "samsung",
    label: "Samsung Health",
    hint: "Oculta la conexión con la cuenta de Samsung para Galaxy Watch (no oficial, beta).",
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

/** Valor de un módulo para una cuenta: "general" (sigue el valor de todos), "on" u "off". */
export type ModuleChoice = "general" | "on" | "off";

export function moduleChoice(
  overrides: Partial<Modules> | undefined,
  key: ModuleKey,
): ModuleChoice {
  const v = overrides?.[key];
  return v === undefined ? "general" : v ? "on" : "off";
}

/** Lo que se manda a la API al elegir: null devuelve la cuenta al valor general. */
export const choiceValue = (choice: ModuleChoice): boolean | null =>
  choice === "general" ? null : choice === "on";

/** ¿Lo tiene activo esta cuenta? Lo propio manda; si no, el valor general. */
export function effectiveModule(
  general: Modules | undefined,
  overrides: Partial<Modules> | undefined,
  key: ModuleKey,
): boolean {
  const own = overrides?.[key];
  return own ?? moduleOn(general, key);
}

/** Resumen corto para la tarjeta del usuario: «IA y Rutas desactivados», «Entrenadores activado»… */
export function overridesSummary(
  overrides: Partial<Modules> | undefined,
): string {
  const on = MODULE_INFO.filter((m) => overrides?.[m.key] === true).map(
    (m) => m.label,
  );
  const off = MODULE_INFO.filter((m) => overrides?.[m.key] === false).map(
    (m) => m.label,
  );
  const join = (xs: string[]) =>
    xs.length > 1
      ? `${xs.slice(0, -1).join(", ")} y ${xs[xs.length - 1]}`
      : xs[0];
  const parts = [
    on.length && `${join(on)} ${on.length > 1 ? "activados" : "activado"}`,
    off.length &&
      `${join(off)} ${off.length > 1 ? "desactivados" : "desactivado"}`,
  ].filter(Boolean);
  return parts.join(" · ");
}

export const moduleLabel = (key: ModuleKey) =>
  MODULE_INFO.find((m) => m.key === key)?.label ?? key;
