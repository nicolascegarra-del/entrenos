import type { RaceGoal } from "@/types/api";

/** Próximo objetivo sin resultado (el de fecha más cercana), si lo hay. */
export function nextGoal(goals: RaceGoal[] | undefined): RaceGoal | null {
  const upcoming = (goals ?? []).filter(
    (g) => g.days_left >= 0 && g.result_time_s == null,
  );
  upcoming.sort((a, b) => a.days_left - b.days_left);
  return upcoming[0] ?? null;
}
