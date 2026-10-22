import { describe, expect, it } from "vitest";

import { deviceLabel, pushSupport, urlBase64ToUint8Array } from "./push";

describe("urlBase64ToUint8Array", () => {
  it("decodifica base64url sin relleno", () => {
    expect(Array.from(urlBase64ToUint8Array("AQID-_8"))).toEqual([
      1, 2, 3, 251, 255,
    ]);
  });
});

describe("pushSupport", () => {
  const base = {
    userAgent: "Mozilla/5.0 (Linux; Android 14) Chrome/130",
    secure: true,
    standalone: false,
    hasPush: true,
  };

  it("Android con Chrome", () => expect(pushSupport(base)).toBe("ok"));
  it("sin HTTPS", () =>
    expect(pushSupport({ ...base, secure: false })).toBe("insecure"));
  it("iPhone sin instalar en la pantalla de inicio", () =>
    expect(
      pushSupport({
        ...base,
        userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Safari/604.1",
      }),
    ).toBe("ios-install"));
  it("iPhone con la app instalada", () =>
    expect(
      pushSupport({
        ...base,
        standalone: true,
        userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Safari/604.1",
      }),
    ).toBe("ok"));
  it("navegador sin Push API", () =>
    expect(pushSupport({ ...base, hasPush: false })).toBe("unsupported"));
});

describe("deviceLabel", () => {
  it("navegador y sistema", () => {
    expect(
      deviceLabel(
        "Mozilla/5.0 (Linux; Android 14) AppleWebKit Chrome/130 Mobile Safari/537",
      ),
    ).toBe("Chrome · Android");
    expect(
      deviceLabel(
        "Mozilla/5.0 (Windows NT 10.0) Chrome/130 Safari/537 Edg/130",
      ),
    ).toBe("Edge · Windows");
  });
});
