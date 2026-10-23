import { describe, expect, it } from "vitest";

import { groupByWeek, weekLabel } from "./weeks";

describe("semanas", () => {
  it("agrupa de lunes a domingo conservando el orden", () => {
    const items = [
      "2026-10-22T08:00:00",
      "2026-10-19T08:00:00",
      "2026-10-18T08:00:00",
      "2026-10-12T08:00:00",
    ];
    const groups = groupByWeek(items, (d) => d);
    expect(groups.map((g) => [g.week, g.items.length])).toEqual([
      ["2026-10-19", 2],
      ["2026-10-12", 2],
    ]);
  });

  it("etiqueta relativa a hoy", () => {
    const today = new Date("2026-10-23T10:00:00");
    expect(weekLabel("2026-10-19", today)).toBe("Esta semana");
    expect(weekLabel("2026-10-12", today)).toBe("Semana pasada");
    expect(weekLabel("2026-09-28", today)).toBe("Semana del 28 sept");
  });
});
