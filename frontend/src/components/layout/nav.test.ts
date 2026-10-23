import { describe, expect, it } from "vitest";

import {
  atSubSectionRoot,
  currentLocation,
  isUnder,
  moreFor,
  screenTitle,
  SECTIONS,
} from "./nav";

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
    expect(where("/ajustes")).toBe("- / -");
  });

  it("las pestañas solo en la portada de cada subsección", () => {
    expect(atSubSectionRoot("/actividades")).toBe(true);
    expect(atSubSectionRoot("/actividades/52")).toBe(false);
  });
});

describe("menú", () => {
  it("4 pestañas abajo más «Más»", () => {
    expect(SECTIONS).toHaveLength(4);
  });

  it("Admin solo para administradores", () => {
    const has = (admin: boolean) =>
      moreFor(admin).some((g) => g.items.some((i) => i.href === "/admin"));
    expect(has(false)).toBe(false);
    expect(has(true)).toBe(true);
  });

  it("título de la cabecera", () => {
    expect(screenTitle("/progresion/rendimiento")).toBe("Progreso");
    expect(screenTitle("/asistente")).toBe("Asistente IA");
    expect(screenTitle("/ajustes")).toBe("Ajustes");
  });
});
