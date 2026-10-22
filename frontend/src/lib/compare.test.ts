import { describe, expect, it } from "vitest";

import { clipPace, gapText, kmTick, signedGap } from "./compare";

describe("comparador", () => {
  it("descarta ritmos de paradas", () => {
    expect(clipPace(320)).toBe(320);
    expect(clipPace(1200)).toBeNull();
    expect(clipPace(null)).toBeNull();
  });

  it("texto de la diferencia (b − a)", () => {
    expect(gapText(-83)).toBe("1:23 más rápida");
    expect(gapText(45)).toBe("0:45 más lenta");
    expect(gapText(0.4)).toBe("igual");
  });

  it("diferencia con signo", () => {
    expect(signedGap(-12)).toBe("−12 s");
    expect(signedGap(65)).toBe("+1:05");
    expect(signedGap(0.2)).toBe("0 s");
  });

  it("marcas del eje en km", () => {
    expect(kmTick(2500)).toBe("2,5 km");
    expect(kmTick(3000)).toBe("3 km");
  });
});
