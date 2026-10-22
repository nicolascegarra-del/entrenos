import {
  CalendarCheck,
  Flame,
  Footprints,
  Medal,
  Mountain,
  Timer,
  Trophy,
  type LucideIcon,
} from "lucide-react";

import type { AchievementKind, AchievementsReport } from "@/types/api";

type Upcoming = AchievementsReport["upcoming"][number];

/** Icono de cada logro según su tipo (y, para los hitos, según su clave). */
export function achievementIcon(
  kind: AchievementKind,
  key: string,
): LucideIcon {
  if (kind === "record") return Timer;
  if (kind === "streak") return Flame;
  if (kind === "challenge") return CalendarCheck;
  if (key.startsWith("elev_")) return Mountain;
  if (key.startsWith("count_")) return Medal;
  if (key.startsWith("first_")) return Footprints;
  return Trophy;
}

export const GROUP_ICON: Record<Upcoming["group"], LucideIcon> = {
  single_run: Footprints,
  run_km: Trophy,
  count: Medal,
  elevation: Mountain,
  streak: Flame,
};

/** «3 semanas» / «1 semana». */
export const weeksText = (n: number) =>
  `${n} ${n === 1 ? "semana" : "semanas"}`;

/** Días que quedan para terminar el reto (incluido hoy). */
export function daysLeft(ends: string, today: Date): number {
  const end = new Date(`${ends}T12:00:00`);
  const start = new Date(today);
  start.setHours(12, 0, 0, 0);
  return Math.max(
    0,
    Math.round((end.getTime() - start.getTime()) / 86400000) + 1,
  );
}

/** Ritmo necesario para cumplir el reto: cuánto falta por día restante. */
export function perDayNeeded(
  current: number,
  target: number,
  days: number,
): number | null {
  if (current >= target || days <= 0) return null;
  return (target - current) / days;
}
