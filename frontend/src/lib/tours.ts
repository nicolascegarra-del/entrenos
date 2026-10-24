/**
 * Tours guiados por la app (Ayuda → Tour): pasos con bocadillo que señalan cada parte de la pantalla.
 *
 * Cada paso apunta a un elemento con `data-tour="<nombre>"`. El mismo nombre puede estar en la versión
 * móvil y en la de escritorio (p. ej. la barra inferior y el sidebar): se usa la que esté visible. Si no hay
 * ninguna, el bocadillo sale centrado, o el paso se salta si es `optional`.
 */

export type TourKey =
  | "general"
  | "hoy"
  | "actividades"
  | "actividad"
  | "plan"
  | "mi-plan"
  | "progreso"
  | "asistente"
  | "ajustes";

export interface TourStep {
  /** Ruta a la que ir antes del paso («actividad»: la primera actividad de la lista). */
  route?: string;
  /** `data-tour` del elemento que se señala (sin él, bocadillo centrado). */
  target?: string;
  title: string;
  body: string;
  /** Si el elemento no está (p. ej. no hay propuestas), se salta el paso en vez de centrarlo. */
  optional?: boolean;
}

export interface Tour {
  key: TourKey;
  title: string;
  summary: string;
  minutes: number;
  /** Pantalla del tour (para el «?» de su cabecera). */
  route: string;
  steps: TourStep[];
}

export const FIRST_ACTIVITY = "actividad";

export const TOURS: Tour[] = [
  {
    key: "general",
    title: "Tour general",
    summary: "Cómo moverte por la app y qué hay en cada sección.",
    minutes: 2,
    route: "/",
    steps: [
      {
        route: "/",
        title: "Te enseño la app",
        body: "En dos minutos te cuento dónde está cada cosa. Puedes salir cuando quieras y repetirlo desde tu cuenta → Tours por la app.",
      },
      {
        target: "nav",
        title: "Cinco secciones",
        body: "Hoy, Entrenos, tu Entrenador (en el centro), Plan y Progreso. Todo lo importante está a uno o dos toques.",
      },
      {
        target: "sync",
        title: "Sincronizar",
        body: "Trae tus últimos entrenos del reloj. Se hace solo cada cierto tiempo, pero aquí lo fuerzas y ves cuándo fue la última vez.",
        optional: true,
      },
      {
        target: "today-card",
        title: "Hoy",
        body: "Cómo llegas (frescura y carga) y qué te toca hoy según tu plan.",
      },
      {
        target: "ask-coach",
        title: "Pregúntale a tu entrenador",
        body: "Escribe aquí o toca una de las preguntas sugeridas: te contesta con todos tus datos.",
        optional: true,
      },
      {
        route: "/asistente",
        target: "tab-entrenador",
        title: "Tu entrenador",
        body: "El chat con tu entrenador IA: le preguntas lo que quieras, te hace la revisión semanal y te propone cambios en el plan. Un punto te avisa cuando tiene algo para ti.",
      },
      {
        route: "/actividades",
        target: "tab-entrenos",
        title: "Entrenos",
        body: "Todas tus actividades, tus recorridos repetidos y tu material (zapatillas).",
      },
      {
        target: "section-tabs",
        title: "Subsecciones",
        body: "Cada sección tiene sus pestañas arriba (en el ordenador, debajo de la sección en el menú).",
      },
      {
        route: "/plan",
        target: "tab-plan",
        title: "Plan",
        body: "Tu calendario de sesiones, el plan automático hacia tu carrera y tus objetivos.",
      },
      {
        route: "/progresion",
        target: "tab-progreso",
        title: "Progreso",
        body: "Tu forma física, rendimiento (ritmos, zonas, marcas) y salud (FC en reposo, HRV, sueño), además de tus logros.",
      },
      {
        target: "account",
        title: "Tu cuenta",
        body: "Ajustes (reloj, perfil, avisos, IA), los tours, el glosario, el modo claro u oscuro y cerrar sesión.",
      },
      {
        target: "tour-help",
        title: "Ayuda en cada pantalla",
        body: "Este «?» te explica la pantalla en la que estás. ¡Listo! Ya conoces la app.",
        optional: true,
      },
    ],
  },
  {
    key: "hoy",
    title: "Hoy",
    summary: "Cómo llegas, qué toca y tu semana.",
    minutes: 1,
    route: "/",
    steps: [
      {
        route: "/",
        target: "today-card",
        title: "Cómo llegas y qué toca",
        body: "Tu frescura y carga reciente, y la sesión de hoy si tienes plan. Pulsa la sesión para ver sus bloques.",
      },
      {
        target: "ask-coach",
        title: "Pregunta rápida",
        body: "Pregúntale a tu entrenador sin salir de Hoy; las sugerencias cambian según tu día.",
        optional: true,
      },
      {
        target: "coach-nudges",
        title: "Tu entrenador",
        body: "Aquí te avisa de la revisión semanal o de cambios que te propone en el plan.",
        optional: true,
      },
      {
        target: "week-kpis",
        title: "Esta semana",
        body: "Kilómetros, tiempo, sesiones y carga de la semana. Debajo despliegas tu forma, VO2max y FC en reposo.",
      },
      {
        target: "streak",
        title: "Racha y retos",
        body: "Semanas seguidas cumpliendo tu objetivo de entrenos y el reto de kilómetros del mes.",
        optional: true,
      },
    ],
  },
  {
    key: "actividades",
    title: "Actividades",
    summary: "Buscar, filtrar, borrar e importar entrenos.",
    minutes: 1,
    route: "/actividades",
    steps: [
      {
        route: "/actividades",
        target: "activity-search",
        title: "Buscar",
        body: "Escribe parte del nombre para encontrar un entreno.",
      },
      {
        target: "sport-filter",
        title: "Filtrar por deporte",
        body: "Carrera, bici, fuerza… Toca para ver solo ese deporte.",
      },
      {
        target: "select-activities",
        title: "Seleccionar y borrar",
        body: "Marca varias y bórralas a la vez. No volverán aunque sincronices.",
        optional: true,
      },
      {
        target: "import",
        title: "Importar",
        body: "Conecta tu reloj (Garmin, COROS, Apple Watch…) o sube ficheros FIT, GPX o TCX.",
      },
    ],
  },
  {
    key: "actividad",
    title: "Detalle de una actividad",
    summary: "Métricas, mapa, zonas, análisis de la IA y exportar.",
    minutes: 1,
    route: "/actividades/",
    steps: [
      {
        route: FIRST_ACTIVITY,
        target: "activity-stats",
        title: "Lo esencial",
        body: "Distancia, tiempo, ritmo, pulso, desnivel y carga. «Todas las métricas» despliega el resto.",
      },
      {
        target: "ai-review",
        title: "Análisis de la IA",
        body: "Tu entrenador te dice cómo fue, qué te aporta y qué mejorar.",
        optional: true,
      },
      {
        target: "activity-zones",
        title: "Zonas, VO2max y parciales",
        body: "Tiempo en cada zona de pulso, tu VO2max y el ritmo de cada kilómetro con la deriva cardiaca.",
        optional: true,
      },
      {
        target: "activity-menu",
        title: "Más opciones",
        body: "Zapatillas, marcarla como carrera o test, exportarla en FIT/TCX/GPX o borrarla.",
      },
      {
        target: "ask-ai",
        title: "Pregúntale a la IA",
        body: "Abre el chat con esta actividad ya preparada para preguntar lo que quieras.",
        optional: true,
      },
    ],
  },
  {
    key: "plan",
    title: "Calendario",
    summary: "Planificar sesiones y enviarlas al reloj.",
    minutes: 1,
    route: "/plan",
    steps: [
      {
        route: "/plan",
        target: "plan-week",
        title: "Tu semana",
        body: "Las sesiones de cada día. Al sincronizar se comparan con lo que hiciste y ves el cumplimiento.",
      },
      {
        target: "new-session",
        title: "Nueva sesión",
        body: "Crea una sesión con bloques (calentamiento, series, recuperación) y objetivos de ritmo, pulso o potencia.",
      },
      {
        target: "send-watch",
        title: "Al reloj",
        body: "Envía las sesiones de los próximos 7 días a tu Garmin o COROS para seguirlas en el reloj.",
        optional: true,
      },
      {
        target: "auto-plan",
        title: "Plan automático",
        body: "Crea un plan hacia tu carrera que se adapta cada semana a cómo vas.",
        optional: true,
      },
    ],
  },
  {
    key: "mi-plan",
    title: "Mi plan",
    summary: "El plan automático hacia tu carrera.",
    minutes: 1,
    route: "/plan/entrenamiento",
    steps: [
      {
        route: "/plan/entrenamiento",
        title: "Tu plan automático",
        body: "Fases, volumen semanal y sesiones hasta tu carrera. Cada semana se ajusta según lo que cumpliste y cómo llegas.",
      },
      {
        target: "section-tabs",
        title: "Calendario y objetivos",
        body: "Desde aquí saltas al calendario o a tus objetivos de carrera.",
      },
    ],
  },
  {
    key: "progreso",
    title: "Progreso",
    summary: "Forma, rendimiento, salud y logros.",
    minutes: 1,
    route: "/progresion",
    steps: [
      {
        route: "/progresion",
        target: "section-tabs",
        title: "Cuatro vistas",
        body: "Forma (carga y frescura), Rendimiento (ritmos, zonas, tests y marcas), Salud y Logros.",
      },
      {
        target: "period",
        title: "Periodo",
        body: "Elige 3 meses, 6 meses o un año: se aplica a todas las gráficas.",
      },
      {
        title: "Toca las gráficas",
        body: "Pasa el dedo o el ratón por encima para ver cada valor; «¿Por qué?» explica de dónde sale cada dato.",
      },
    ],
  },
  {
    key: "asistente",
    title: "Entrenador IA",
    summary: "Tu entrenador personal: chat, ficha y revisión semanal.",
    minutes: 1,
    route: "/asistente",
    steps: [
      {
        route: "/asistente",
        target: "chat-input",
        title: "Pregúntale",
        body: "Mira todos tus datos (entrenos, pulso, zonas, plan) y te explica en qué se basa.",
      },
      {
        target: "interview",
        title: "Entrevista inicial",
        body: "Te hace unas preguntas para conocerte y lo guarda en tu ficha.",
        optional: true,
      },
      {
        target: "weekly-review",
        title: "Revisión semanal",
        body: "El domingo te pregunta qué tal la semana y te dice qué toca.",
      },
      {
        title: "Lo que sabe de ti",
        body: "Lo que te pregunta y guarda lo ves y lo corriges en Ajustes → Asistente IA → «Lo que sé de ti».",
      },
    ],
  },
  {
    key: "ajustes",
    title: "Ajustes",
    summary: "Reloj, perfil, avisos, IA y cuenta.",
    minutes: 1,
    route: "/ajustes",
    steps: [
      {
        route: "/ajustes",
        target: "settings-list",
        title: "Todo en secciones",
        body: "Cada sección muestra su estado: si el reloj está conectado, si tienes avisos, qué IA usas…",
      },
      {
        title: "Conexiones",
        body: "En Conexiones eliges tu reloj (Garmin, COROS, Apple Watch, Android o ficheros) y el envío automático de sesiones.",
      },
    ],
  },
];

export const tourByKey = (key: string): Tour | undefined =>
  TOURS.find((t) => t.key === key);

/** Tour de la pantalla actual (para el «?» de la cabecera); el general no va en ninguna. */
export function tourForPath(pathname: string): Tour | undefined {
  if (/^\/actividades\/\d+$/.test(pathname)) return tourByKey("actividad");
  return TOURS.find((t) => t.key !== "general" && t.route === pathname);
}

const SEEN_KEY = "tours-vistos";

export function seenTours(
  storage: Pick<Storage, "getItem"> | null,
): Set<string> {
  try {
    const raw = JSON.parse(storage?.getItem(SEEN_KEY) ?? "[]");
    return new Set(
      Array.isArray(raw) ? raw.filter((x) => typeof x === "string") : [],
    );
  } catch {
    return new Set();
  }
}

export function markSeen(
  storage: Pick<Storage, "getItem" | "setItem"> | null,
  key: string,
): void {
  try {
    const seen = seenTours(storage);
    seen.add(key);
    storage?.setItem(SEEN_KEY, JSON.stringify([...seen]));
  } catch {
    // Sin almacenamiento (modo privado): da igual, solo es para el «visto».
  }
}

/** Siguiente paso a mostrar desde `from` (saltando los opcionales cuyo elemento no está). */
export function nextIndex(
  steps: TourStep[],
  from: number,
  dir: 1 | -1,
  present: (target: string) => boolean,
): number | null {
  for (let i = from + dir; i >= 0 && i < steps.length; i += dir) {
    const s = steps[i];
    if (!s.optional || !s.target || s.route || present(s.target)) return i;
  }
  return null;
}
