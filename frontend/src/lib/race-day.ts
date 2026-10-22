import { formatNumber } from "@/lib/format";

/** «+2,1 %» / «−0,8 %» / «0 %». */
export function signedPct(v: number): string {
  if (Math.abs(v) < 0.05) return "0 %";
  return `${v > 0 ? "+" : "−"}${formatNumber(Math.abs(v), 1)} %`;
}

/** «a los 40 min» / «a los 30, 56 y 82 min». */
export function minutesList(mins: number[]): string {
  if (!mins.length) return "";
  if (mins.length === 1) return `a los ${mins[0]} min`;
  return `a los ${mins.slice(0, -1).join(", ")} y ${mins[mins.length - 1]} min`;
}

/** Leer un fichero de texto (GPX) en el navegador. */
export function readText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result ?? ""));
    r.onerror = () => reject(new Error("No se pudo leer el fichero."));
    r.readAsText(file);
  });
}
