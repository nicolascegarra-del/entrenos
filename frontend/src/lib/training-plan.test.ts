import { describe, expect, it } from "vitest";

import { isQuality, planDaysValid } from "./training-plan";

describe("planDaysValid", () => {
  it("al menos 2 días y la tirada larga en uno de ellos", () => {
    expect(planDaysValid([1, 3, 6], 6)).toBe(true);
    expect(planDaysValid([1, 3], 6)).toBe(false);
    expect(planDaysValid([6], 6)).toBe(false);
  });
});

describe("isQuality", () => {
  it("umbral, series y ritmo de carrera son de calidad", () => {
    expect(isQuality("threshold")).toBe(true);
    expect(isQuality("easy")).toBe(false);
    expect(isQuality(null)).toBe(false);
  });
});
