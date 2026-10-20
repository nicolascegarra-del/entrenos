import {
  BookOpen,
  CalendarDays,
  Flag,
  Footprints,
  LayoutDashboard,
  Settings,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** En móvil: pestaña de la barra inferior o entrada del panel «Más». */
  mobile: "tab" | "more";
  /** Solo visible para administradores. */
  admin?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Resumen", icon: LayoutDashboard, mobile: "tab" },
  {
    href: "/actividades",
    label: "Actividades",
    icon: Footprints,
    mobile: "tab",
  },
  { href: "/plan", label: "Plan", icon: CalendarDays, mobile: "tab" },
  { href: "/progresion", label: "Progresión", icon: TrendingUp, mobile: "tab" },
  { href: "/objetivos", label: "Objetivos", icon: Flag, mobile: "more" },
  { href: "/asistente", label: "Asistente IA", icon: Sparkles, mobile: "more" },
  { href: "/glosario", label: "Glosario", icon: BookOpen, mobile: "more" },
  { href: "/ajustes", label: "Ajustes", icon: Settings, mobile: "more" },
  {
    href: "/admin",
    label: "Admin",
    icon: ShieldCheck,
    mobile: "more",
    admin: true,
  },
];

export const MOBILE_TABS = NAV_ITEMS.filter((i) => i.mobile === "tab");
export const MOBILE_MORE = NAV_ITEMS.filter((i) => i.mobile === "more");

/** Entradas visibles según el rol (Admin solo para administradores). */
export const visibleFor = (items: NavItem[], isAdmin: boolean) =>
  items.filter((i) => !i.admin || isAdmin);

/** Indica si la ruta actual pertenece a la sección `href` (incluye subpáginas). */
export function isActive(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
