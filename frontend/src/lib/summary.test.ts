import { describe, expect, it } from "vitest";

import type { RaceGoal } from "@/types/api";

import { GLOSSARY } from "./glossary";
import { nextGoal } from "./summary";

const goal = (
  id: number,
  days_left: number,
  result_time_s: number | null = null,
): RaceGoal => ({
  id,
  name: `Objetivo ${id}`,
  race_date: "2026-11-01",
  distance_m: 10000,
  target_time_s: null,
  result_activity_id: null,
  result_time_s,
  predicted_time_s: null,
  probable_s: null,
  days_left,
});

describe("nextGoal", () => {
  it("elige el objetivo futuro más cercano", () => {
    expect(nextGoal([goal(1, 40), goal(2, 12), goal(3, 90)])?.id).toBe(2);
  });

  it("ignora los pasados y los que ya tienen resultado", () => {
    expect(nextGoal([goal(1, -3), goal(2, 5, 2900)])).toBeNull();
  });

  it("sin objetivos devuelve null", () => {
    expect(nextGoal(undefined)).toBeNull();
  });
});

describe("glosario", () => {
  it("cada entrada explica qué es y cómo leerla", () => {
    for (const entry of Object.values(GLOSSARY)) {
      expect(entry.name.length).toBeGreaterThan(0);
      expect(entry.what.length).toBeGreaterThan(20);
      expect(entry.read.length).toBeGreaterThan(20);
    }
  });
});
