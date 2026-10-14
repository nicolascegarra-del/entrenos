import { describe, expect, it } from "vitest";

import {
  blockSummary,
  formatTarget,
  parseClock,
  startOfWeek,
  toIsoDay,
} from "@/lib/plan";
import type { PlannedBlock } from "@/types/api";

const base: PlannedBlock = {
  kind: "interval",
  repeat: 1,
  duration_s: null,
  distance_m: null,
  target_metric: null,
  target_min: null,
  target_max: null,
  recovery_duration_s: null,
  recovery_distance_m: null,
};

describe("plan", () => {
  it("parseClock cuando m:ss, h:mm:ss o minutos entonces segundos", () => {
    expect(parseClock("4:15")).toBe(255);
    expect(parseClock("1:05:30")).toBe(3930);
    expect(parseClock("10")).toBe(600);
    expect(parseClock("4:75")).toBeNull();
    expect(parseClock("abc")).toBeNull();
    expect(parseClock("")).toBeNull();
  });

  it("blockSummary cuando series con objetivo y recuperación entonces texto compacto", () => {
    const block = {
      ...base,
      repeat: 6,
      distance_m: 1000,
      target_metric: "pace" as const,
      target_min: 240,
      target_max: 250,
      recovery_duration_s: 90,
    };
    expect(blockSummary(block)).toBe("6 × 1,00 km @ 4:00–4:10 /km · rec. 1:30");
  });

  it("formatTarget cuando solo máximo entonces ≤", () => {
    expect(formatTarget("hr", null, 150)).toBe("≤ 150 ppm");
  });

  it("startOfWeek cuando domingo entonces lunes anterior", () => {
    expect(toIsoDay(startOfWeek(new Date(2026, 9, 18)))).toBe("2026-10-12");
    expect(toIsoDay(startOfWeek(new Date(2026, 9, 12)))).toBe("2026-10-12");
  });
});
