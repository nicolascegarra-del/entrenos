import { describe, expect, it } from "vitest";

import type { ZoneSet } from "@/types/api";

import { durationLabel } from "./pace-curve";
import { zonesChange } from "./zones-card";

const zone = (lthr: number, pace: number): ZoneSet => ({
  valid_from: "2026-10-01",
  thresholds: {
    lthr,
    lthr_source: "garmin",
    threshold_pace_s_km: pace,
    pace_source: "vdot",
    vdot: 40,
  },
  zones: { hr: [], pace: [] },
});

describe("zonesChange", () => {
  it("describe el cambio de umbrales", () => {
    expect(zonesChange(zone(165, 290), zone(162, 298))).toEqual([
      "FC umbral +3 ppm",
      "ritmo umbral 8 s/km más rápido",
    ]);
  });

  it("sin cambios no dice nada", () => {
    expect(zonesChange(zone(160, 300), zone(160, 300))).toEqual([]);
  });
});

describe("durationLabel", () => {
  it("minutos y horas", () => {
    expect(durationLabel(300)).toBe("5 min");
    expect(durationLabel(3600)).toBe("1 h");
  });
});
