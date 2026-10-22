import { describe, expect, it } from "vitest";

import { minutesList, signedPct } from "./race-day";

describe("día de carrera", () => {
  it("porcentajes con signo", () => {
    expect(signedPct(2.06)).toBe("+2,1 %");
    expect(signedPct(-0.8)).toBe("−0,8 %");
    expect(signedPct(0.01)).toBe("0 %");
  });

  it("lista de minutos de los geles", () => {
    expect(minutesList([])).toBe("");
    expect(minutesList([40])).toBe("a los 40 min");
    expect(minutesList([30, 56, 82])).toBe("a los 30, 56 y 82 min");
  });
});
