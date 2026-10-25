/**
 * Lógica pura del editor de rutas (sin mapa ni red): puntos de paso, ida y vuelta, circular, y la posición
 * en el mapa de un punto del perfil de altura.
 */

export type LatLon = [number, number];

export const MAX_ROUTE_POINTS = 25;

export type RouteMode = "asfalto" | "trail" | "bici" | "mtb";

export const ROUTE_MODES: { key: RouteMode; label: string; hint: string }[] = [
  { key: "asfalto", label: "Asfalto", hint: "Calles y carreteras para correr" },
  { key: "trail", label: "Trail", hint: "Senderos y caminos de montaña" },
  { key: "bici", label: "Bici", hint: "Carretera en bici" },
  { key: "mtb", label: "MTB", hint: "Pistas y caminos en bici de montaña" },
];

/** Añade un punto al final (el último es siempre el fin de la ruta). */
export function addPoint(points: LatLon[], p: LatLon): LatLon[] {
  return points.length >= MAX_ROUTE_POINTS ? points : [...points, p];
}

export function movePoint(
  points: LatLon[],
  index: number,
  p: LatLon,
): LatLon[] {
  return points.map((q, i) => (i === index ? p : q));
}

export function removePoint(points: LatLon[], index: number): LatLon[] {
  return points.filter((_, i) => i !== index);
}

const same = (a: LatLon, b: LatLon) =>
  Math.abs(a[0] - b[0]) < 1e-6 && Math.abs(a[1] - b[1]) < 1e-6;

/** Vuelve al inicio por el mismo camino (repite los puntos al revés). Null si no cabe en el límite. */
export function outAndBack(points: LatLon[]): LatLon[] | null {
  if (points.length < 2) return null;
  const back = points.slice(0, -1).reverse();
  const result = [...points, ...back];
  return result.length > MAX_ROUTE_POINTS ? null : result;
}

/** Cierra la ruta en el inicio (circular). */
export function closeLoop(points: LatLon[]): LatLon[] {
  if (points.length < 2 || same(points[0], points[points.length - 1]))
    return points;
  return points.length >= MAX_ROUTE_POINTS ? points : [...points, points[0]];
}

export const isLoop = (points: LatLon[]) =>
  points.length > 2 && same(points[0], points[points.length - 1]);

function haversine(a: LatLon, b: LatLon): number {
  const rad = Math.PI / 180;
  const dLat = (b[0] - a[0]) * rad;
  const dLon = (b[1] - a[1]) * rad;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6_371_000 * Math.asin(Math.sqrt(h));
}

/** Punto de la traza a `meters` del inicio (para seguir en el mapa el perfil de altura). */
export function pointAtDistance(
  geometry: (number | null)[][],
  meters: number,
): LatLon | null {
  if (!geometry.length) return null;
  let acc = 0;
  for (let i = 1; i < geometry.length; i++) {
    const a: LatLon = [
      geometry[i - 1][0] as number,
      geometry[i - 1][1] as number,
    ];
    const b: LatLon = [geometry[i][0] as number, geometry[i][1] as number];
    const d = haversine(a, b);
    if (acc + d >= meters) {
      const t = d ? (meters - acc) / d : 0;
      return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    }
    acc += d;
  }
  const last = geometry[geometry.length - 1];
  return [last[0] as number, last[1] as number];
}

/** «8,4 km · +320 m / −310 m» */
export function routeStats(
  distance_m: number,
  ascent_m: number,
  descent_m: number,
) {
  const km = (distance_m / 1000).toLocaleString("es-ES", {
    maximumFractionDigits: distance_m < 10_000 ? 2 : 1,
  });
  return `${km} km · +${ascent_m} m / −${descent_m} m`;
}
