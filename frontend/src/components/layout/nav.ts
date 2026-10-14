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
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Resumen", icon: LayoutDashboard },
  { href: "/actividades", label: "Actividades", icon: Footprints },
  { href: "/plan", label: "Plan", icon: CalendarDays },
  { href: "/objetivos", label: "Objetivos", icon: Flag },
  { href: "/progresion", label: "Progresión", icon: TrendingUp },
  { href: "/ajustes", label: "Ajustes", icon: Settings },
];
