import {
  CalendarDays,
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
  { href: "/progresion", label: "Progresión", icon: TrendingUp },
  { href: "/ajustes", label: "Ajustes", icon: Settings },
];
