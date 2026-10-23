import { describe, expect, it } from "vitest";

import type { PerformanceTest, TestProtocol } from "@/types/api";

import {
  isActive,
  parsePace,
  protocolsFor,
  testSport,
  testValues,
} from "./tests";

const protocol = (
  key: string,
  sport: TestProtocol["sport"],
  detectable = true,
) =>
  ({
    key,
    sport,
    detectable,
    label: key,
    summary: "",
    how: "",
    template: [],
  }) as TestProtocol;

describe("testSport y protocolsFor", () => {
  it("agrupa los deportes de la actividad", () => {
    expect(testSport("treadmill_running")).toBe("running");
    expect(testSport("indoor_cycling")).toBe("cycling");
    expect(testSport("lap_swimming")).toBe("swimming");
    expect(testSport("strength_training")).toBeNull();
  });

  it("solo los detectables del mismo deporte", () => {
    const all = [
      protocol("run_30min", "running"),
      protocol("bike_hr_30min", "cycling"),
      protocol("manual", "running", false),
    ];
    expect(protocolsFor(all, "trail_running").map((p) => p.key)).toEqual([
      "run_30min",
    ]);
    expect(protocolsFor(all, "yoga")).toEqual([]);
    expect(protocolsFor(undefined, "running")).toEqual([]);
  });
});

describe("testValues", () => {
  it("ordena y da formato a los valores", () => {
    const v = testValues({ lthr: 170, threshold_pace_s_km: 250, vo2max: 53.1 });
    expect(v.map((x) => x.value)).toEqual(["4:10 /km", "170 ppm", "53,1"]);
  });
});

describe("isActive", () => {
  const test = (status: PerformanceTest["status"], test_date: string) =>
    ({ status, test_date }) as PerformanceTest;
  it("confirmado y de las últimas 8 semanas", () => {
    const today = new Date("2026-10-23T12:00:00");
    expect(isActive(test("confirmed", "2026-10-01"), today)).toBe(true);
    expect(isActive(test("confirmed", "2026-08-01"), today)).toBe(false);
    expect(isActive(test("detected", "2026-10-20"), today)).toBe(false);
  });
});

describe("parsePace", () => {
  it("m:ss a segundos", () => {
    expect(parsePace("4:05")).toBe(245);
    expect(parsePace("")).toBeNull();
    expect(parsePace("4.05")).toBeNaN();
  });
});
