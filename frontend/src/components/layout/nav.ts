import {
  CalendarDays,
  Flag,
  Footprints,
  LayoutDashboard,
  Settings,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** En móvil: pestaña de la barra inferior o entrada del panel «Más». */
  mobile: "tab" | "more";
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
  { href: "/ajustes", label: "Ajustes", icon: Settings, mobile: "more" },
];

export const MOBILE_TABS = NAV_ITEMS.filter((i) => i.mobile === "tab");
export const MOBILE_MORE = NAV_ITEMS.filter((i) => i.mobile === "more");

/** Indica si la ruta actual pertenece a la sección `href` (incluye subpáginas). */
export function isActive(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
