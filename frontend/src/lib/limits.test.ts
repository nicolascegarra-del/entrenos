import { describe, expect, it } from "vitest";

import { describeLimits } from "./limits";

describe("describeLimits", () => {
  it("cuenta Completa: sin límites", () => {
    expect(
      describeLimits({
        history_days: null,
        max_goals: null,
        max_sessions_week: null,
      }),
    ).toEqual([]);
  });

  it("cuenta Básica: frases en singular y plural", () => {
    expect(
      describeLimits({
        history_days: 180,
        max_goals: 1,
        max_sessions_week: 14,
      }),
    ).toEqual([
      "últimos 180 días de Garmin",
      "hasta 1 objetivo activo",
      "hasta 14 sesiones por semana",
    ]);
  });
});
