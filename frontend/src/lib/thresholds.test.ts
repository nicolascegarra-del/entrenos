import { describe, expect, it } from "vitest";

import { thresholdAlternatives } from "./thresholds";

describe("thresholdAlternatives", () => {
  it("ordena de más rápida a más lenta y marca la elegida", () => {
    expect(
      thresholdAlternatives(
        { vdot: 418, garmin: 400, mejor_hora: 405 },
        "garmin",
      ),
    ).toEqual([
      { key: "garmin", label: "Garmin", pace: "6:40 /km", chosen: true },
      {
        key: "mejor_hora",
        label: "Tu mejor hora",
        pace: "6:45 /km",
        chosen: false,
      },
      {
        key: "vdot",
        label: "Daniels (tu nivel de carrera)",
        pace: "6:58 /km",
        chosen: false,
      },
    ]);
  });

  it("sin datos, lista vacía", () => {
    expect(thresholdAlternatives(undefined, null)).toEqual([]);
  });
});
