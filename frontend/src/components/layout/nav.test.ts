import { describe, expect, it } from "vitest";

import { LOADING_MODULES, type Modules } from "@/lib/modules";

import {
  atSubSectionRoot,
  bottomSections,
  currentLocation,
  isUnder,
  accountFor,
  progressInMenu,
  screenTitle,
  SECTIONS,
} from "./nav";

const ON: Modules = { ...LOADING_MODULES };
const SOCIAL_OFF: Modules = { ...LOADING_MODULES, social: false };

describe("isUnder", () => {
  it("Hoy solo en la raíz", () => {
    expect(isUnder("/", "/")).toBe(true);
    expect(isUnder("/", "/plan")).toBe(false);
  });

  it("incluye subpáginas y no confunde prefijos", () => {
    expect(isUnder("/plan", "/plan/12/editar")).toBe(true);
    expect(isUnder("/plan", "/planes")).toBe(false);
  });
});

describe("currentLocation", () => {
  const where = (path: string) => {
    const { section, sub } = currentLocation(path);
    return `${section?.label ?? "-"} / ${sub?.label ?? "-"}`;
  };

  it("cada ruta cae en su pestaña y subsección", () => {
    expect(where("/")).toBe("Hoy / -");
    expect(where("/actividades/52")).toBe("Entrenos / Actividades");
    expect(where("/comparar")).toBe("Entrenos / Recorridos");
    expect(where("/material")).toBe("Entrenos / Material");
    expect(where("/plan/3/editar")).toBe("Plan / Calendario");
    expect(where("/plan/entrenamiento")).toBe("Plan / Mi plan");
    expect(where("/plan/generar")).toBe("Plan / Mi plan");
    expect(where("/objetivos/4")).toBe("Plan / Objetivos");
    expect(where("/progresion")).toBe("Progreso / Forma");
    expect(where("/progresion/salud")).toBe("Progreso / Salud");
    expect(where("/logros")).toBe("Progreso / Logros");
    expect(where("/social")).toBe("Amigos / Feed");
    expect(where("/social/ranking")).toBe("Amigos / Clasificación");
    expect(where("/social/duelos")).toBe("Amigos / Duelos");
    expect(where("/social/personas")).toBe("Amigos / Personas");
    expect(where("/u/ana.run")).toBe("Amigos / Personas");
    expect(where("/ajustes")).toBe("- / -");
  });

  it("las pestañas solo en la portada de cada subsección", () => {
    expect(atSubSectionRoot("/actividades")).toBe(true);
    expect(atSubSectionRoot("/actividades/52")).toBe(false);
  });
});

describe("menú", () => {
  it("en el PC, todas las secciones (Progreso incluido) en el lateral", () => {
    expect(SECTIONS.map((s) => s.key)).toEqual([
      "hoy",
      "entrenos",
      "entrenador",
      "plan",
      "amigos",
      "progreso",
    ]);
  });

  it("test_barra_movil_cuando_amigos_activo_entonces_ocupa_el_sitio_de_progreso", () => {
    const keys = bottomSections(ON).map((s) => s.key);
    expect(keys).toEqual(["hoy", "entrenos", "entrenador", "plan", "amigos"]);
    // El entrenador sigue en el centro.
    expect(keys[2]).toBe("entrenador");
    expect(progressInMenu(ON)).toBe(true);
    expect(accountFor(false, true)[0].items.map((i) => i.href)).toEqual([
      "/progresion",
    ]);
    // Mientras cargan los módulos, como con Amigos activo (sin parpadeos).
    expect(bottomSections(undefined).map((s) => s.key)).toContain("amigos");
  });

  it("test_barra_movil_cuando_amigos_apagado_entonces_vuelve_progreso", () => {
    expect(bottomSections(SOCIAL_OFF).map((s) => s.key)).toEqual([
      "hoy",
      "entrenos",
      "entrenador",
      "plan",
      "progreso",
    ]);
    expect(progressInMenu(SOCIAL_OFF)).toBe(false);
    expect(
      accountFor(false, false).some((g) =>
        g.items.some((i) => i.href === "/progresion"),
      ),
    ).toBe(false);
  });

  it("el entrenador abre su pestaña", () => {
    expect(currentLocation("/asistente/semana").section?.key).toBe(
      "entrenador",
    );
  });

  it("Admin solo para administradores", () => {
    const has = (admin: boolean) =>
      accountFor(admin).some((g) => g.items.some((i) => i.href === "/admin"));
    expect(has(false)).toBe(false);
    expect(has(true)).toBe(true);
  });

  it("título de la cabecera", () => {
    expect(screenTitle("/progresion/rendimiento")).toBe("Progreso");
    expect(screenTitle("/asistente")).toBe("Entrenador");
    expect(screenTitle("/social/duelos")).toBe("Amigos");
    expect(screenTitle("/ayuda")).toBe("Tours por la app");
    expect(screenTitle("/ajustes")).toBe("Ajustes");
  });
});
