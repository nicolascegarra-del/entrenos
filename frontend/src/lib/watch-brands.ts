import type {
  AppleImport,
  DevicesStatus,
  GarminStatus,
  OuraStatus,
  SourcesStatus,
} from "@/types/api";

export type WatchBrand =
  | "garmin"
  | "apple"
  | "coros"
  | "suunto"
  | "zepp"
  | "xiaomi"
  | "android"
  | "oura"
  | "files";

/** Marcas que se conectan con la cuenta de su marca (cada una con su módulo). */
export const DEVICE_BRANDS = ["suunto", "zepp", "xiaomi"] as const;

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
  { key: "suunto", label: "Suunto", how: "Con tu cuenta de Suunto" },
  { key: "zepp", label: "Amazfit", how: "Con tu cuenta de Zepp" },
  {
    key: "xiaomi",
    label: "Xiaomi Smart Band y Redmi Watch",
    how: "Con un QR desde la app de Xiaomi (beta)",
  },
  {
    key: "android",
    label: "Samsung, Huawei, Wear OS",
    how: "Desde el móvil Android con Health Connect",
  },
  {
    key: "oura",
    label: "Oura Ring",
    how: "Anillo: sueño, recuperación y actividad",
  },
  {
    key: "files",
    label: "Polar, Wahoo y otros",
    how: "Importando ficheros FIT, GPX o TCX",
  },
];

/** Marcas que ya tienen algo conectado o importado (se muestran marcadas). */
export function connectedBrands(
  garmin: GarminStatus | undefined,
  sources: SourcesStatus | undefined,
  apple: AppleImport | null | undefined,
  oura?: OuraStatus,
  devices?: DevicesStatus,
): WatchBrand[] {
  const out: WatchBrand[] = [];
  if (garmin?.connected || garmin?.connection.status === "expired")
    out.push("garmin");
  if (sources?.apple_last_at || apple?.status === "done") out.push("apple");
  if (sources?.coros || sources?.coros_official) out.push("coros");
  if (sources?.health_connect?.last_used_at) out.push("android");
  if (oura?.connected || oura?.status === "expired") out.push("oura");
  for (const c of devices?.connections ?? [])
    if (c.status !== "pending") out.push(c.provider);
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
export function otherWatch(
  sources: SourcesStatus | undefined,
  devices?: DevicesStatus,
): string | null {
  const device = devices?.connections.find((c) => c.status === "ok");
  if (device) return DEVICE_NAMES[device.provider];
  if (!sources) return null;
  if (sources.apple_last_at) return "Apple Watch";
  if (sources.coros || sources.coros_official) return "COROS";
  if (sources.health_connect?.last_used_at) return "Health Connect";
  return null;
}

const DEVICE_NAMES: Record<(typeof DEVICE_BRANDS)[number], string> = {
  suunto: "Suunto",
  zepp: "Amazfit",
  xiaomi: "Xiaomi",
};

export interface ConnectedDevices {
  /** Nombres de lo conectado (y funcionando), en el orden de `WATCH_BRANDS`. */
  connected: string[];
  /** Conexiones caducadas o con error: hay que volver a conectarlas. */
  broken: string[];
  /** «Ningún dispositivo conectado», «1 dispositivo conectado: Oura», «2 dispositivos conectados: Garmin, Oura». */
  label: string;
}

/**
 * Todo lo que está conectado (relojes, anillo y pulseras), no solo Garmin: es el estado de Ajustes →
 * Conexiones. Los ficheros importados a mano no cuentan como dispositivo.
 */
export function connectedDevices({
  garmin,
  sources,
  oura,
  devices,
}: {
  garmin?: GarminStatus;
  sources?: SourcesStatus;
  oura?: OuraStatus;
  devices?: DevicesStatus;
}): ConnectedDevices {
  const connected: string[] = [];
  const broken: string[] = [];
  if (garmin?.connected) connected.push("Garmin");
  else if (garmin?.connection.status === "expired") broken.push("Garmin");
  if (sources?.apple_last_at) connected.push("Apple Watch");
  const coros = sources?.coros_official ?? sources?.coros;
  if (coros) (coros.status === "ok" ? connected : broken).push("COROS");
  for (const key of DEVICE_BRANDS) {
    const c = devices?.connections.find((d) => d.provider === key);
    if (!c || c.status === "pending") continue;
    (c.status === "ok" ? connected : broken).push(DEVICE_NAMES[key]);
  }
  if (sources?.health_connect?.last_used_at) connected.push("Health Connect");
  if (oura?.connected && oura.status !== "expired") connected.push("Oura");
  else if (oura?.status === "expired") broken.push("Oura");
  const n = connected.length;
  const label =
    n === 0
      ? "Ningún dispositivo conectado"
      : `${n} ${n === 1 ? "dispositivo conectado" : "dispositivos conectados"}: ${connected.join(", ")}`;
  return { connected, broken, label };
}
