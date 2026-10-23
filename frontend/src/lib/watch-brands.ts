import type { AppleImport, GarminStatus, SourcesStatus } from "@/types/api";

export type WatchBrand = "garmin" | "apple" | "coros" | "android" | "files";

/** Marcas de reloj y cómo se conecta cada una (en el orden en que se muestran). */
export const WATCH_BRANDS: {
  key: WatchBrand;
  label: string;
  how: string;
}[] = [
  { key: "garmin", label: "Garmin", how: "Con tu cuenta de Garmin Connect" },
  {
    key: "apple",
    label: "Apple Watch",
    how: "Export de la app Salud y un Atajo diario",
  },
  { key: "coros", label: "COROS", how: "Con tu cuenta de COROS" },
  {
    key: "android",
    label: "Samsung, Xiaomi, Huawei, Wear OS",
    how: "Desde el móvil Android con Health Connect",
  },
  {
    key: "files",
    label: "Suunto, Polar, Wahoo y otros",
    how: "Importando ficheros FIT, GPX o TCX",
  },
];

/** Marcas que ya tienen algo conectado o importado (se muestran marcadas). */
export function connectedBrands(
  garmin: GarminStatus | undefined,
  sources: SourcesStatus | undefined,
  apple: AppleImport | null | undefined,
): WatchBrand[] {
  const out: WatchBrand[] = [];
  if (garmin?.connected || garmin?.connection.status === "expired")
    out.push("garmin");
  if (sources?.apple_last_at || apple?.status === "done") out.push("apple");
  if (sources?.coros || sources?.coros_official) out.push("coros");
  if (sources?.health_connect?.last_used_at) out.push("android");
  return out;
}

/** Une lo elegido a mano con lo ya conectado, sin repetir y en el orden de `WATCH_BRANDS`. */
export function mergeBrands(
  chosen: WatchBrand[],
  connected: WatchBrand[],
): WatchBrand[] {
  const set = new Set([...chosen, ...connected]);
  return WATCH_BRANDS.map((b) => b.key).filter((k) => set.has(k));
}

/** Lee la selección guardada (ignora valores que no sean marcas conocidas). */
export function parseBrands(raw: string | null): WatchBrand[] {
  try {
    const value: unknown = JSON.parse(raw ?? "[]");
    const keys = WATCH_BRANDS.map((b) => b.key) as string[];
    return Array.isArray(value)
      ? (value.filter((v) => keys.includes(v)) as WatchBrand[])
      : [];
  } catch {
    return [];
  }
}

/** Reloj conectado por una vía que no es Garmin (para los estados de Ajustes y de Hoy). */
export function otherWatch(sources: SourcesStatus | undefined): string | null {
  if (!sources) return null;
  if (sources.apple_last_at) return "Apple Watch";
  if (sources.coros) return "COROS";
  if (sources.health_connect?.last_used_at) return "Health Connect";
  return null;
}
