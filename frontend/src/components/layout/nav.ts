import {
  BookOpen,
  CircleHelp,
  CalendarDays,
  Footprints,
  LayoutDashboard,
  Settings,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Users,
  type LucideIcon,
} from "lucide-react";

import {
  filterByModule,
  moduleOn,
  type ModuleKey,
  type Modules,
} from "@/lib/modules";

/** Subsección de una pestaña (pestañas superiores). `paths` = rutas que también le pertenecen. */
export interface SubSection {
  href: string;
  label: string;
  paths?: string[];
  /** Solo se ve si este módulo está activo. */
  module?: ModuleKey;
}

/** Pestaña principal: barra inferior en el móvil y grupo del sidebar en escritorio. */
export interface Section {
  key: "hoy" | "entrenos" | "entrenador" | "plan" | "amigos" | "progreso";
  href: string;
  label: string;
  icon: LucideIcon;
  children: SubSection[];
  /** Solo se ve si este módulo está activo. */
  module?: ModuleKey;
}

export interface MoreLink {
  href: string;
  label: string;
  icon: LucideIcon;
  admin?: boolean;
}

/**
 * Las pestañas de la app y sus subsecciones. Fuente única para barra inferior, sidebar y pestañas.
 * El entrenador va en el centro de la barra del móvil. En el móvil caben 5: con Amigos activo,
 * Amigos ocupa el sitio de Progreso y Progreso pasa al menú de la cuenta (ver `bottomSections`).
 */
export const SECTIONS: Section[] = [
  { key: "hoy", href: "/", label: "Hoy", icon: LayoutDashboard, children: [] },
  {
    key: "entrenos",
    href: "/actividades",
    label: "Entrenos",
    icon: Footprints,
    children: [
      { href: "/actividades", label: "Actividades" },
      { href: "/recorridos", label: "Recorridos", paths: ["/comparar"] },
      { href: "/material", label: "Material" },
    ],
  },
  {
    key: "entrenador",
    href: "/asistente",
    label: "Entrenador",
    icon: Sparkles,
    children: [],
    module: "ia",
  },
  {
    key: "plan",
    href: "/plan",
    label: "Plan",
    icon: CalendarDays,
    children: [
      { href: "/plan", label: "Calendario" },
      {
        href: "/plan/entrenamiento",
        label: "Mi plan",
        paths: ["/plan/generar"],
      },
      { href: "/plan/rutas", label: "Rutas", module: "rutas" },
      { href: "/objetivos", label: "Objetivos" },
    ],
  },
  {
    key: "amigos",
    href: "/social",
    label: "Amigos",
    icon: Users,
    module: "social",
    children: [
      { href: "/social", label: "Feed" },
      { href: "/social/ranking", label: "Clasificación" },
      { href: "/social/duelos", label: "Duelos" },
      // Los perfiles públicos (/u/@handle) cuelgan de Personas.
      { href: "/social/personas", label: "Personas", paths: ["/u"] },
    ],
  },
  {
    key: "progreso",
    href: "/progresion",
    label: "Progreso",
    icon: TrendingUp,
    children: [
      { href: "/progresion", label: "Forma" },
      { href: "/progresion/rendimiento", label: "Rendimiento" },
      { href: "/progresion/salud", label: "Salud" },
      { href: "/logros", label: "Logros" },
    ],
  },
];

/** Menú de cuenta (avatar de la cabecera en el móvil, parte baja del sidebar en el PC), por grupos. */
export const ACCOUNT_GROUPS: { title: string; items: MoreLink[] }[] = [
  {
    title: "Cuenta",
    items: [
      { href: "/ajustes", label: "Ajustes", icon: Settings },
      { href: "/admin", label: "Admin", icon: ShieldCheck, admin: true },
    ],
  },
  {
    title: "Ayuda",
    items: [
      { href: "/ayuda", label: "Tours por la app", icon: CircleHelp },
      { href: "/glosario", label: "Glosario", icon: BookOpen },
    ],
  },
];

/** ¿La ruta `pathname` está en `base` o por debajo? (sin confundir /plan con /planes). */
export function isUnder(base: string, pathname: string): boolean {
  if (base === "/") return pathname === "/";
  return pathname === base || pathname.startsWith(`${base}/`);
}

/** Compatibilidad: activo si la ruta pertenece a `href`. */
export const isActive = (href: string, pathname: string) =>
  isUnder(href, pathname);

/**
 * Subsección en la que estás: gana la ruta más larga que encaje (así /plan/entrenamiento es «Mi plan»
 * y no «Calendario», aunque las dos empiecen por /plan).
 */
export function currentLocation(pathname: string): {
  section: Section | null;
  sub: SubSection | null;
} {
  let best: { section: Section; sub: SubSection | null; len: number } | null =
    null;
  for (const section of SECTIONS) {
    const candidates = section.children.length
      ? section.children.flatMap((sub) =>
          [sub.href, ...(sub.paths ?? [])].map((p) => ({ sub, p })),
        )
      : [{ sub: null, p: section.href }];
    for (const { sub, p } of candidates) {
      if (isUnder(p, pathname) && (!best || p.length > best.len))
        best = { section, sub, len: p.length };
    }
  }
  return { section: best?.section ?? null, sub: best?.sub ?? null };
}

/** ¿Estás exactamente en la portada de una subsección (no en un detalle)? Ahí se ven las pestañas. */
export const atSubSectionRoot = (pathname: string) =>
  SECTIONS.some((s) => s.children.some((c) => c.href === pathname));

/** Pestañas y subsecciones visibles según los módulos activos (cargando = como estaban). */
export const visibleSections = (modules: Modules | undefined): Section[] =>
  filterByModule(SECTIONS, modules).map((s) => ({
    ...s,
    children: filterByModule(s.children, modules),
  }));

/**
 * Pestañas de la barra inferior del móvil (máximo 5): si Amigos está visible ocupa el sitio de
 * Progreso, que pasa al menú de la cuenta. Con el módulo apagado, Progreso vuelve a la barra.
 */
export function bottomSections(modules: Modules | undefined): Section[] {
  const visible = visibleSections(modules);
  return visible.some((s) => s.key === "amigos")
    ? visible.filter((s) => s.key !== "progreso")
    : visible;
}

/** ¿Progreso va en el menú de la cuenta del móvil? (cuando Amigos le quita el sitio en la barra). */
export const progressInMenu = (modules: Modules | undefined) =>
  moduleOn(modules, "social");

/** Enlace a Progreso para el menú de la cuenta del móvil. */
export const PROGRESS_LINK: MoreLink = {
  href: "/progresion",
  label: "Progreso",
  icon: TrendingUp,
};

/**
 * Grupos del menú de cuenta visibles según el rol (Admin solo para administradores).
 * `withProgress` añade Progreso al principio (menú del móvil con Amigos en la barra).
 */
export const accountFor = (isAdmin: boolean, withProgress = false) =>
  [
    ...(withProgress ? [{ title: "Secciones", items: [PROGRESS_LINK] }] : []),
    ...ACCOUNT_GROUPS,
  ]
    .map((g) => ({
      ...g,
      items: g.items.filter((i) => !i.admin || isAdmin),
    }))
    .filter((g) => g.items.length);

/** Título de la pantalla para la cabecera móvil. */
export function screenTitle(pathname: string): string {
  const { section } = currentLocation(pathname);
  if (section) return section.label;
  const more = ACCOUNT_GROUPS.flatMap((g) => g.items).find((i) =>
    isUnder(i.href, pathname),
  );
  if (more) return more.label;
  if (isUnder("/bienvenida", pathname)) return "Bienvenida";
  return "KTrain";
}
