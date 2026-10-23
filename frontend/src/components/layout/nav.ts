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
  type LucideIcon,
} from "lucide-react";

/** Subsección de una pestaña (pestañas superiores). `paths` = rutas que también le pertenecen. */
export interface SubSection {
  href: string;
  label: string;
  paths?: string[];
}

/** Pestaña principal: barra inferior en el móvil y grupo del sidebar en escritorio. */
export interface Section {
  key: "hoy" | "entrenos" | "plan" | "progreso";
  href: string;
  label: string;
  icon: LucideIcon;
  children: SubSection[];
}

export interface MoreLink {
  href: string;
  label: string;
  icon: LucideIcon;
  admin?: boolean;
}

/** Las 4 pestañas de la app y sus subsecciones. Fuente única para barra inferior, sidebar y pestañas. */
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
      { href: "/objetivos", label: "Objetivos" },
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

/** Panel «Más» (móvil) y parte baja del sidebar, por grupos. */
export const MORE_GROUPS: { title: string | null; items: MoreLink[] }[] = [
  {
    title: null,
    items: [{ href: "/asistente", label: "Asistente IA", icon: Sparkles }],
  },
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

/** Grupos del «Más» visibles según el rol (Admin solo para administradores). */
export const moreFor = (isAdmin: boolean) =>
  MORE_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((i) => !i.admin || isAdmin),
  })).filter((g) => g.items.length);

/** Título de la pantalla para la cabecera móvil. */
export function screenTitle(pathname: string): string {
  const { section } = currentLocation(pathname);
  if (section) return section.label;
  const more = MORE_GROUPS.flatMap((g) => g.items).find((i) =>
    isUnder(i.href, pathname),
  );
  if (more) return more.label;
  if (isUnder("/bienvenida", pathname)) return "Bienvenida";
  return "APP ENTRENOS";
}
