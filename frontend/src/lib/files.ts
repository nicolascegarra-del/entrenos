/** Bytes → base64 (por trozos, para no desbordar la pila con ficheros grandes). */
export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export const IMPORT_EXTENSIONS = [".fit", ".gpx", ".tcx"];

/** ¿Se puede importar por la extensión? */
export const importable = (name: string) =>
  IMPORT_EXTENSIONS.some((ext) => name.toLowerCase().endsWith(ext));

export async function fileToBase64(file: File): Promise<string> {
  return bytesToBase64(new Uint8Array(await file.arrayBuffer()));
}
