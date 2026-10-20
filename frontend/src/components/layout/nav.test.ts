import { describe, expect, it } from "vitest";

import {
  isActive,
  MOBILE_MORE,
  MOBILE_TABS,
  NAV_ITEMS,
  visibleFor,
} from "./nav";

describe("isActive", () => {
  it("resumen solo en la raíz", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/", "/plan")).toBe(false);
  });

  it("incluye subpáginas de la sección", () => {
    expect(isActive("/plan", "/plan/12/editar")).toBe(true);
    expect(isActive("/objetivos", "/objetivos")).toBe(true);
  });

  it("no confunde secciones con el mismo prefijo", () => {
    expect(isActive("/plan", "/planes")).toBe(false);
  });
});

describe("navegación móvil", () => {
  it("cabe en la barra inferior: 4 pestañas más «Más»", () => {
    expect(MOBILE_TABS).toHaveLength(4);
    expect(MOBILE_TABS.length + MOBILE_MORE.length).toBe(NAV_ITEMS.length);
  });
});

describe("visibleFor", () => {
  it("Admin solo aparece a los administradores", () => {
    expect(visibleFor(NAV_ITEMS, false).some((i) => i.href === "/admin")).toBe(
      false,
    );
    expect(visibleFor(NAV_ITEMS, true).some((i) => i.href === "/admin")).toBe(
      true,
    );
  });
});
