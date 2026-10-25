import { describe, expect, it } from "vitest";

import type {
  CoachSettings,
  GarminStatus,
  InjuryReport,
  Profile,
} from "@/types/api";

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

  const profile = (over: Partial<Profile> = {}) =>
    ({
      birth_date: null,
      sex: null,
      weight_kg: null,
      height_cm: null,
      hr_max_source: "tanaka",
      ...over,
    }) as Profile;
  const coach = (interview_done: boolean) =>
    ({ interview_done }) as CoachSettings;

  it("primero el reloj; la entrevista avisa si aún no hay datos o sincroniza", () => {
    const none = setupSteps({
      garmin: garmin("none"),
      sources: SOURCES,
      coach: coach(false),
      hasAi: true,
      hasActivities: false,
    });
    expect(none.map((s) => s.key)).toEqual(["watch", "interview"]);
    expect(none[1].hint).toContain("después de conectar el reloj");
    const syncing = setupSteps({
      garmin: {
        ...garmin("ok"),
        last_run: { status: "running" },
      } as GarminStatus,
      coach: coach(false),
      hasAi: true,
    });
    expect(syncing[0].hint).toContain("Espera a que termine");
    const ready = setupSteps({
      garmin: garmin("ok"),
      coach: coach(false),
      hasAi: true,
      hasActivities: true,
    });
    expect(ready[0].hint).toContain("datos que ha sacado de tus entrenos");
  });

  it("con IA: la entrevista inicial completa la ficha", () => {
    const steps = setupSteps({
      profile: profile(),
      coach: coach(false),
      hasAi: true,
    });
    expect(steps.map((s) => s.key)).toEqual(["interview"]);
    expect(steps[0].href).toBe("/asistente?modo=entrevista");
    expect(
      setupSteps({ profile: profile(), coach: coach(true), hasAi: true }),
    ).toEqual([]);
  });

  it("sin IA: perfil y umbrales a mano", () => {
    const steps = setupSteps({
      profile: profile({ sex: "male" }),
      hasAi: false,
    });
    expect(steps.map((s) => s.key)).toEqual(["profile", "thresholds"]);
    expect(steps[0].hint).toContain("fecha de nacimiento, peso, altura");
    expect(
      setupSteps({
        profile: profile({
          birth_date: "1985-04-12",
          sex: "male",
          weight_kg: 70,
          height_cm: 178,
          hr_max_source: "real",
        }),
        hasAi: false,
      }),
    ).toEqual([]);
  });
});
