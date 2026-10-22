import { describe, expect, it } from "vitest";

import {
  achievementIcon,
  daysLeft,
  perDayNeeded,
  weeksText,
} from "./achievements";

describe("logros", () => {
  it("icono por tipo y clave", () => {
    expect(achievementIcon("record", "pr:best_5k:1").displayName).toBe(
      achievementIcon("record", "x").displayName,
    );
    expect(achievementIcon("milestone", "elev_1000")).not.toBe(
      achievementIcon("milestone", "count_10"),
    );
  });

  it("singular y plural de semanas", () => {
    expect(weeksText(1)).toBe("1 semana");
    expect(weeksText(4)).toBe("4 semanas");
  });

  it("días restantes del reto, incluido hoy", () => {
    expect(daysLeft("2026-10-31", new Date("2026-10-22T09:00:00"))).toBe(10);
    expect(daysLeft("2026-10-01", new Date("2026-10-22T09:00:00"))).toBe(0);
  });

  it("lo que falta por día", () => {
    expect(perDayNeeded(30, 50, 10)).toBe(2);
    expect(perDayNeeded(50, 50, 10)).toBeNull();
    expect(perDayNeeded(10, 50, 0)).toBeNull();
  });
});
