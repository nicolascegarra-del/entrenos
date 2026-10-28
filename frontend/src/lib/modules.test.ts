import { describe, expect, it } from "vitest";

import { SECTIONS, visibleSections } from "@/components/layout/nav";
import type { CoachSettings, Profile } from "@/types/api";

import {
  choiceValue,
  disabledModuleFor,
  effectiveModule,
  filterByModule,
  LOADING_MODULES,
  MODULE_INFO,
  moduleChoice,
  moduleOn,
  overridesSummary,
  type Modules,
} from "./modules";
import { setupSteps } from "./notices";
import { tourByKey, tourForPath, toursFor, TOURS } from "./tours";

const ALL_ON: Modules = {
  entrenadores: true,
  ia: true,
  reloj: true,
  rutas: true,
  nutricion: true,
};
const off = (...keys: (keyof Modules)[]): Modules => ({
  ...ALL_ON,
  ...Object.fromEntries(keys.map((k) => [k, false])),
});

describe("moduleOn", () => {
  it("cuando aún no hay datos, entonces como estaba (lo existente visible)", () => {
    expect(moduleOn(undefined, "ia")).toBe(true);
    expect(moduleOn(undefined, "rutas")).toBe(true);
    expect(moduleOn(undefined, "nutricion")).toBe(false);
    expect(LOADING_MODULES.entrenadores).toBe(false);
  });

  it("sin módulo, siempre visible; con módulo, lo que diga el administrador", () => {
    expect(moduleOn(off("ia"), undefined)).toBe(true);
    expect(moduleOn(off("ia"), "ia")).toBe(false);
    expect(moduleOn(off("ia"), "reloj")).toBe(true);
  });

  it("filterByModule quita solo los apagados", () => {
    const items = [{ id: 1 }, { id: 2, module: "ia" as const }];
    expect(filterByModule(items, off("ia")).map((i) => i.id)).toEqual([1]);
    expect(filterByModule(items, ALL_ON)).toHaveLength(2);
  });

  it("cada módulo tiene su explicación para el panel", () => {
    // Entrenadores y nutrición no existen en esta rama: no salen en el panel.
    expect(MODULE_INFO.map((m) => m.key).sort()).toEqual(
      Object.keys(ALL_ON)
        .filter((k) => k !== "entrenadores" && k !== "nutricion")
        .sort(),
    );
    MODULE_INFO.forEach((m) => expect(m.hint.length).toBeGreaterThan(10));
  });
});

describe("disabledModuleFor", () => {
  it("cuando el módulo está apagado, entonces la pantalla no se enseña", () => {
    expect(disabledModuleFor("/asistente", off("ia"))).toBe("ia");
    expect(disabledModuleFor("/asistente/semana", off("ia"))).toBe("ia");
    expect(disabledModuleFor("/ajustes/asistente", off("ia"))).toBe("ia");
    expect(disabledModuleFor("/plan/rutas/3", off("rutas"))).toBe("rutas");
  });

  it("cuando está activo, cargando o la ruta es otra, entonces se ve", () => {
    expect(disabledModuleFor("/asistente", ALL_ON)).toBeNull();
    expect(disabledModuleFor("/asistente", undefined)).toBeNull();
    expect(disabledModuleFor("/plan", off("rutas"))).toBeNull();
    expect(disabledModuleFor("/asistentes", off("ia"))).toBeNull();
  });
});

describe("visibleSections", () => {
  it("cuando la IA está apagada, entonces no hay pestaña del entrenador", () => {
    const keys = visibleSections(off("ia")).map((s) => s.key);
    expect(keys).toEqual(["hoy", "entrenos", "plan", "progreso"]);
  });

  it("cuando las rutas están apagadas, entonces Plan no tiene «Rutas»", () => {
    const plan = visibleSections(off("rutas")).find((s) => s.key === "plan")!;
    expect(plan.children.map((c) => c.label)).not.toContain("Rutas");
    expect(plan.children.length).toBeGreaterThan(1);
  });

  it("cuando carga, entonces todo como estaba", () => {
    expect(visibleSections(undefined)).toEqual(SECTIONS);
  });
});

describe("toursFor", () => {
  it("cuando la IA está apagada, entonces sin tour ni pasos del entrenador", () => {
    const tours = toursFor(off("ia"));
    expect(tours.map((t) => t.key)).not.toContain("asistente");
    const targets = tours.flatMap((t) => t.steps.map((s) => s.target));
    for (const t of [
      "ask-coach",
      "tab-entrenador",
      "coach-nudges",
      "ai-review",
      "ask-ai",
    ])
      expect(targets).not.toContain(t);
    expect(tourByKey("asistente", off("ia"))).toBeUndefined();
    expect(tourForPath("/asistente", off("ia"))).toBeUndefined();
  });

  it("cuando el reloj está apagado, entonces sin el paso «Al reloj»", () => {
    const plan = tourByKey("plan", off("reloj"))!;
    expect(plan.steps.map((s) => s.target)).not.toContain("send-watch");
  });

  it("cuando carga, entonces los tours de siempre", () => {
    expect(toursFor(undefined)).toEqual(TOURS);
  });
});

describe("setupSteps con el módulo de IA", () => {
  const profile = {
    birth_date: null,
    sex: "male",
    weight_kg: null,
    height_cm: null,
    hr_max_source: "tanaka",
  } as Profile;
  const coach = { interview_done: false } as CoachSettings;

  it("cuando la IA está apagada, entonces sin entrevista y con perfil a mano", () => {
    const keys = setupSteps({
      profile,
      coach,
      hasAi: true,
      iaModule: false,
    }).map((s) => s.key);
    expect(keys).not.toContain("interview");
    expect(keys).toEqual(["profile", "thresholds"]);
  });

  it("cuando está activa, entonces la entrevista de siempre", () => {
    expect(
      setupSteps({ profile, coach, hasAi: true, iaModule: true }).map(
        (s) => s.key,
      ),
    ).toEqual(["interview"]);
  });
});

describe("módulos por cuenta", () => {
  const general: Modules = { ...LOADING_MODULES, ia: false };

  it("lo propio de la cuenta manda sobre el valor general", () => {
    expect(effectiveModule(general, { ia: true }, "ia")).toBe(true);
    expect(effectiveModule(general, {}, "ia")).toBe(false);
    expect(effectiveModule(general, { rutas: false }, "rutas")).toBe(false);
  });

  it("traduce entre la elección y lo que se manda a la API", () => {
    expect(moduleChoice({}, "ia")).toBe("general");
    expect(moduleChoice({ ia: false }, "ia")).toBe("off");
    expect(choiceValue("general")).toBeNull();
    expect(choiceValue("on")).toBe(true);
  });

  it("resume lo fijado para la tarjeta del usuario", () => {
    expect(overridesSummary({})).toBe("");
    expect(overridesSummary({ ia: false, rutas: false, reloj: true })).toBe(
      "Envío al reloj activado · Entrenador IA y Rutas desactivados",
    );
  });
});
