import { ApiError, apiFetch, authFetch, parseError } from "@/lib/api";
import type { AppleImport } from "@/types/api";

const BASE = "/api/v1/imports/apple-health";
const RETRIES = 3;

/** ¿Parece el export de Apple Salud? (el zip tal cual o el export.xml descomprimido) */
export const isAppleExport = (name: string) =>
  /\.(zip|xml)$/i.test(name.trim());

/**
 * Sube el export de Apple Salud a trozos (cuerpo binario) y lo deja en cola para procesarlo.
 * Si un trozo falla se reintenta; si el servidor tiene otro punto de reanudación (409), se sigue desde ahí.
 * @param file - export.zip (o export.xml).
 * @param onProgress - fracción subida, de 0 a 1.
 * @param signal - para cancelar la subida.
 * @returns La importación ya en cola.
 */
export async function uploadAppleExport(
  file: File,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<AppleImport> {
  const started = await apiFetch<AppleImport>(BASE, {
    method: "POST",
    body: JSON.stringify({ filename: file.name, size_bytes: file.size }),
  });
  let offset = 0;
  let failures = 0;
  while (offset < file.size) {
    signal?.throwIfAborted();
    const chunk = file.slice(offset, offset + started.chunk_bytes);
    try {
      const res = await authFetch(`${BASE}/${started.id}?offset=${offset}`, {
        method: "PUT",
        body: chunk,
        headers: { "Content-Type": "application/octet-stream" },
        signal,
      });
      if (res.status === 409) {
        // El servidor ya tenía otra parte: reanudar desde lo que dice tener.
        const latest = await apiFetch<AppleImport | null>(BASE);
        if (latest?.id !== started.id || latest.status !== "uploading")
          throw await parseError(res);
        offset = latest.received_bytes;
        continue;
      }
      if (!res.ok) throw await parseError(res);
      offset = ((await res.json()) as AppleImport).received_bytes;
      failures = 0;
      onProgress(offset / file.size);
    } catch (err) {
      if (signal?.aborted || (err instanceof ApiError && err.status < 500))
        throw err;
      failures += 1;
      if (failures > RETRIES) throw err;
      await new Promise((r) => setTimeout(r, 1000 * failures));
    }
  }
  return apiFetch<AppleImport>(`${BASE}/${started.id}/finish`, {
    method: "POST",
  });
}
