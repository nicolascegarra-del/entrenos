import { describe, expect, it } from "vitest";

import { needsOnboarding, ONBOARDING_STEPS, stepIndex } from "./onboarding";

describe("stepIndex", () => {
  it("encuentra el paso del parámetro", () => {
    expect(stepIndex("perfil")).toBe(2);
    expect(ONBOARDING_STEPS[stepIndex("listo")].label).toBe("Listo");
  });

  it("sin parámetro o con uno desconocido empieza por la bienvenida", () => {
    expect(stepIndex(null)).toBe(0);
    expect(stepIndex("otro")).toBe(0);
  });
});

describe("needsOnboarding", () => {
  it("solo cuentas sin configurar y fuera de /bienvenida", () => {
    expect(needsOnboarding({ onboarded: false }, "/")).toBe(true);
    expect(needsOnboarding({ onboarded: false }, "/bienvenida")).toBe(false);
    expect(needsOnboarding({ onboarded: true }, "/")).toBe(false);
    expect(needsOnboarding(undefined, "/")).toBe(false);
  });
});
