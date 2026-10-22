import type { Gear, GearInput, GearStatus } from "@/types/api";

/** Texto del estado de unas zapatillas (siempre junto a icono o barra, nunca solo color). */
export const GEAR_STATUS: Record<GearStatus, string> = {
  ok: "En buen estado",
  soon: "Casi al límite",
  replace: "Para cambiar",
  retired: "Retiradas",
};

/** Porcentaje de vida útil gastado (0–100) respecto al límite de aviso. */
export function gearUsedPct(g: Pick<Gear, "total_km" | "alert_km">): number {
  if (g.alert_km <= 0) return 100;
  return Math.min(100, Math.max(0, (g.total_km / g.alert_km) * 100));
}

/** Kilómetros que quedan hasta el límite (negativo si ya se ha pasado). */
export const gearKmLeft = (g: Pick<Gear, "total_km" | "alert_km">) =>
  Math.round((g.alert_km - g.total_km) * 10) / 10;

/** Valores del formulario a partir de unas zapatillas (o vacíos para el alta). */
export function gearForm(g?: Gear): GearInput {
  return {
    name: g?.name ?? "",
    brand: g?.brand ?? "",
    model: g?.model ?? "",
    start_km: g?.start_km ?? 0,
    alert_km: g?.alert_km ?? 700,
    first_use: g?.first_use ?? null,
    is_default: g?.is_default ?? false,
    retired: g?.retired ?? false,
  };
}

/** Las zapatillas solo se asignan a carreras (asfalto, trail o cinta). */
export const usesShoes = (sport: string) => sport.includes("running");
