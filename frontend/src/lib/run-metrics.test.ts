import { describe, expect, it } from "vitest";

import { conditionText, efficiencyText, intensityText } from "./run-metrics";

describe("indicadores de carrera", () => {
  it("efficiencyText compara con tu media o explica que faltan carreras", () => {
    const base = { value: 1.3, baseline: 1.25, baseline_runs: 6, by_km: [] };
    expect(efficiencyText({ ...base, delta_pct: 4 })).toMatch(
      /\+4 % más eficiente/,
    );
    expect(efficiencyText({ ...base, delta_pct: -3 })).toMatch(
      /menos eficiente/,
    );
    expect(efficiencyText({ ...base, delta_pct: null })).toMatch(
      /hacen falta 3/,
    );
  });

  it("conditionText lee el valor y avisa si cae durante la carrera", () => {
    const c = { source: "reloj" as const, series: [] as [number, number][] };
    expect(conditionText({ ...c, initial: 6, final: 5, min: 4 })).toMatch(
      /Muy buen día/,
    );
    expect(conditionText({ ...c, initial: 2, final: -5, min: -5 })).toMatch(
      /Fue bajando/,
    );
    expect(
      conditionText({ ...c, initial: -8, final: null, min: null }),
    ).toMatch(/descansa/);
  });

  it("intensityText por bandas del umbral", () => {
    expect(intensityText(0.7)).toBe("Suave");
    expect(intensityText(1)).toBe("En umbral");
    expect(intensityText(null)).toMatch(/Sin FC/);
  });
});
