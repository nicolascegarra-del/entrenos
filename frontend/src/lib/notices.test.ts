import { describe, expect, it } from "vitest";

import type { GarminStatus, InjuryReport } from "@/types/api";

import { buildNotices, setupSteps } from "./notices";

const garmin = (status: "none" | "ok" | "expired") =>
  ({
    connected: status === "ok",
    connection: {
      status,
      display_name: null,
      connected_at: null,
      last_ok_at: null,
    },
    last_run: null,
  }) as GarminStatus;

const injury = (status: "good" | "watch" | "alert"): InjuryReport => ({
  status,
  summary: "Resumen",
  week_km: 20,
  disclaimer: "",
  checks: [
    {
      key: "volume",
      status,
      title: "Volumen +35 %",
      message: "Baja la próxima semana.",
      evidence: [],
    },
    {
      key: "shoes",
      status: "good",
      title: "Zapatillas bien",
      message: "",
      evidence: [],
    },
  ],
});

describe("buildNotices", () => {
  it("Garmin caducado primero y el riesgo de lesión después", () => {
    const n = buildNotices({
      garmin: garmin("expired"),
      injury: injury("alert"),
    });
    expect(n.map((x) => x.key)).toEqual(["garmin", "injury"]);
    expect(n[1].title).toBe("Volumen +35 %");
  });

  it("sin nada que vigilar, sin avisos", () => {
    expect(
      buildNotices({ garmin: garmin("ok"), injury: injury("good") }),
    ).toEqual([]);
  });
});

const SOURCES = {
  coros: null,
  health_connect: null,
  ingest_url: "",
  apple_shortcut_url: "",
  apple_last_at: null,
};

describe("setupSteps", () => {
  it("lo que falta por configurar", () => {
    const steps = setupSteps({
      garmin: garmin("none"),
      goals: [],
      gear: [],
      sources: SOURCES,
    });
    expect(steps.map((s) => s.key)).toEqual(["watch", "goal", "gear"]);
  });

  it("no pide conectar reloj si ya llega algo de Apple Watch u otro", () => {
    const steps = setupSteps({
      garmin: garmin("none"),
      sources: { ...SOURCES, apple_last_at: "2026-10-01T07:00:00Z" },
    });
    expect(steps).toEqual([]);
  });

  it("si aún no han cargado los datos, no se muestra nada", () => {
    expect(setupSteps({})).toEqual([]);
  });
});
