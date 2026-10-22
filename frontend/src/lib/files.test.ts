import { describe, expect, it } from "vitest";

import { bytesToBase64, importable } from "./files";

describe("ficheros", () => {
  it("base64 de bytes, también grandes", () => {
    expect(bytesToBase64(new Uint8Array([0, 1, 2, 250]))).toBe("AAEC+g==");
    const big = new Uint8Array(100_000).fill(65);
    expect(atob(bytesToBase64(big))).toHaveLength(100_000);
  });

  it("extensiones admitidas", () => {
    expect(importable("Carrera.FIT")).toBe(true);
    expect(importable("ruta.gpx")).toBe(true);
    expect(importable("foto.jpg")).toBe(false);
  });
});
