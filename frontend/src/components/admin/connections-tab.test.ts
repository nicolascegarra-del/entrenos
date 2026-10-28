import { describe, expect, it } from "vitest";

import type { OuraAppSettings } from "@/types/api";

import { ouraSourceText } from "./connections-tab";

const base: OuraAppSettings = {
  configured: false,
  source: null,
  client_id: "",
  has_secret: false,
  has_webhook_token: false,
  redirect_uris: [],
  webhook_url: "",
  webhooks: "",
};

describe("ouraSourceText", () => {
  it("dice de dónde salen las credenciales", () => {
    expect(ouraSourceText(base)).toMatch(/Sin configurar/);
    expect(ouraSourceText({ ...base, source: "panel" })).toMatch(/panel/);
    expect(ouraSourceText({ ...base, source: "entorno" })).toMatch(
      /variables de entorno/,
    );
  });
});
