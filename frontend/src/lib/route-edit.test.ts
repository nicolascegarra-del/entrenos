import { describe, expect, it } from "vitest";

import {
  addPoint,
  closeLoop,
  isLoop,
  type LatLon,
  MAX_ROUTE_POINTS,
  movePoint,
  outAndBack,
  pointAtDistance,
  removePoint,
  routeStats,
} from "./route-edit";

const A: LatLon = [37.6, -0.98];
const B: LatLon = [37.61, -0.97];
const C: LatLon = [37.62, -0.96];

describe("route-edit", () => {
  it("añade, mueve y quita puntos sin pasar del límite", () => {
    expect(addPoint([A], B)).toEqual([A, B]);
    expect(movePoint([A, B], 1, C)).toEqual([A, C]);
    expect(removePoint([A, B, C], 1)).toEqual([A, C]);
    const full = Array.from({ length: MAX_ROUTE_POINTS }, (): LatLon => A);
    expect(addPoint(full, B)).toHaveLength(MAX_ROUTE_POINTS);
  });

  it("ida y vuelta y circular", () => {
    expect(outAndBack([A, B, C])).toEqual([A, B, C, B, A]);
    expect(outAndBack([A])).toBeNull();
    expect(closeLoop([A, B, C])).toEqual([A, B, C, A]);
    expect(isLoop(closeLoop([A, B, C]))).toBe(true);
    expect(closeLoop([A, B, A])).toEqual([A, B, A]);
  });

  it("sigue el perfil sobre la traza", () => {
    const geometry = [
      [37.6, -0.98, 100],
      [37.61, -0.98, 120],
    ];
    const mid = pointAtDistance(geometry, 556);
    expect(mid?.[0]).toBeCloseTo(37.605, 3);
    expect(pointAtDistance(geometry, 99_999)).toEqual([37.61, -0.98]);
    expect(pointAtDistance([], 10)).toBeNull();
  });

  it("resumen de distancia y desnivel", () => {
    expect(routeStats(8420, 320, 310)).toBe("8,42 km · +320 m / −310 m");
    expect(routeStats(21_100, 50, 50)).toBe("21,1 km · +50 m / −50 m");
  });
});
