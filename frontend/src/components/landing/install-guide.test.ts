import { describe, expect, it } from "vitest";

import { detectPlatform } from "./install-guide";

describe("detectPlatform", () => {
  it("reconoce el dispositivo para abrir sus instrucciones", () => {
    expect(
      detectPlatform("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)"),
    ).toBe("ios");
    // iPadOS se presenta como Mac, pero con pantalla táctil.
    expect(
      detectPlatform("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)", 5),
    ).toBe("ios");
    expect(
      detectPlatform("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)", 0),
    ).toBe("desktop");
    expect(detectPlatform("Mozilla/5.0 (Linux; Android 15; Pixel 9)")).toBe(
      "android",
    );
    expect(detectPlatform("Mozilla/5.0 (Windows NT 10.0; Win64; x64)")).toBe(
      "desktop",
    );
  });
});
