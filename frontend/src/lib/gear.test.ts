import { describe, expect, it } from "vitest";

import { gearForm, gearKmLeft, gearUsedPct, usesShoes } from "./gear";

describe("vida útil de las zapatillas", () => {
  it("porcentaje gastado acotado entre 0 y 100", () => {
    expect(gearUsedPct({ total_km: 350, alert_km: 700 })).toBe(50);
    expect(gearUsedPct({ total_km: 900, alert_km: 700 })).toBe(100);
    expect(gearUsedPct({ total_km: 10, alert_km: 0 })).toBe(100);
  });

  it("km restantes, negativos si se ha pasado", () => {
    expect(gearKmLeft({ total_km: 650.25, alert_km: 700 })).toBe(49.8);
    expect(gearKmLeft({ total_km: 720, alert_km: 700 })).toBe(-20);
  });
});

describe("formulario", () => {
  it("alta con 700 km de límite por defecto", () => {
    expect(gearForm()).toMatchObject({ name: "", alert_km: 700, start_km: 0 });
  });
});

describe("usesShoes", () => {
  it("solo para carreras", () => {
    expect(usesShoes("trail_running")).toBe(true);
    expect(usesShoes("cycling")).toBe(false);
  });
});
