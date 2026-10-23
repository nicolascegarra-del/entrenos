import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { SECTIONS } from "@/components/layout/nav";

import {
  FIRST_ACTIVITY,
  markSeen,
  nextIndex,
  seenTours,
  tourByKey,
  tourForPath,
  TOURS,
} from "./tours";

/** Todos los `data-tour="…"` del código (para no dejar pasos apuntando a nada). */
function anchorsInSource(dir = join(__dirname, "..")): Set<string> {
  const found = new Set<string>();
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      anchorsInSource(path).forEach((a) => found.add(a));
    } else if (/\.tsx$/.test(name)) {
      for (const m of readFileSync(path, "utf8").matchAll(
        /data-tour="([a-z-]+)"/g,
      ))
        found.add(m[1]);
      // Las pestañas de sección usan data-tour={`tab-${key}`}.
      if (readFileSync(path, "utf8").includes("data-tour={`tab-$"))
        SECTIONS.forEach((s) => found.add(`tab-${s.key}`));
    }
  }
  return found;
}

describe("tours", () => {
  it("claves únicas y pasos con título y texto", () => {
    const keys = TOURS.map((t) => t.key);
    expect(new Set(keys).size).toBe(keys.length);
    for (const t of TOURS) {
      expect(t.steps.length).toBeGreaterThan(1);
      for (const s of t.steps) {
        expect(s.title.length).toBeGreaterThan(2);
        expect(s.body.length).toBeGreaterThan(10);
      }
      // El primer paso lleva a la pantalla del tour.
      expect(t.steps[0].route).toBeDefined();
    }
  });

  it("cada elemento señalado existe en el código", () => {
    const anchors = anchorsInSource();
    const missing = TOURS.flatMap((t) => t.steps)
      .map((s) => s.target)
      .filter((x): x is string => !!x && !anchors.has(x));
    expect(missing).toEqual([]);
  });

  it("las rutas son pantallas de la app", () => {
    const routes = TOURS.flatMap((t) => t.steps)
      .map((s) => s.route)
      .filter((r): r is string => !!r);
    for (const r of routes)
      expect(r === FIRST_ACTIVITY || r.startsWith("/")).toBe(true);
  });

  it("el «?» de cada pantalla encuentra su tour", () => {
    expect(tourForPath("/")?.key).toBe("hoy");
    expect(tourForPath("/actividades/42")?.key).toBe("actividad");
    expect(tourForPath("/progresion")?.key).toBe("progreso");
    expect(tourForPath("/glosario")).toBeUndefined();
    expect(tourByKey("general")?.minutes).toBe(2);
  });

  it("salta los pasos opcionales sin elemento", () => {
    const steps = [
      { title: "a", body: "x", route: "/" },
      { title: "b", body: "x", target: "uno", optional: true },
      { title: "c", body: "x", target: "dos" },
    ];
    expect(nextIndex(steps, 0, 1, () => false)).toBe(2);
    expect(nextIndex(steps, 0, 1, () => true)).toBe(1);
    expect(nextIndex(steps, 2, 1, () => true)).toBeNull();
    expect(nextIndex(steps, 2, -1, () => false)).toBe(0);
  });

  it("recuerda los tours vistos", () => {
    const store = new Map<string, string>();
    const storage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
    };
    markSeen(storage, "hoy");
    markSeen(storage, "general");
    expect([...seenTours(storage)].sort()).toEqual(["general", "hoy"]);
    expect(seenTours(null).size).toBe(0);
  });
});
