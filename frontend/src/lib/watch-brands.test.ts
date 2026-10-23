import { describe, expect, it } from "vitest";

import type { GarminStatus, SourcesStatus } from "@/types/api";

import { connectedBrands, mergeBrands, parseBrands } from "./watch-brands";

const garmin = (connected: boolean, status: "none" | "ok" | "expired") =>
  ({
    connected,
    connection: {
      status,
      display_name: null,
      connected_at: null,
      last_ok_at: null,
    },
    last_run: null,
  }) as GarminStatus;

const sources = (patch: Partial<SourcesStatus> = {}): SourcesStatus => ({
  coros: null,
  health_connect: null,
  ingest_url: "",
  apple_shortcut_url: "",
  apple_last_at: null,
  ...patch,
});

describe("connectedBrands", () => {
  it("sin nada conectado no marca ninguna", () => {
    expect(connectedBrands(garmin(false, "none"), sources(), null)).toEqual([]);
  });

  it("marca Garmin aunque haya caducado, y Apple al llegar algo", () => {
    expect(
      connectedBrands(
        garmin(false, "expired"),
        sources({ apple_last_at: "2026-10-01T07:00:00Z" }),
        null,
      ),
    ).toEqual(["garmin", "apple"]);
  });

  it("Android solo cuando Health Connect ya ha enviado datos", () => {
    const hc = { hint: "abcd", created_at: "", last_used_at: null };
    expect(
      connectedBrands(undefined, sources({ health_connect: hc }), null),
    ).toEqual([]);
    expect(
      connectedBrands(
        undefined,
        sources({ health_connect: { ...hc, last_used_at: "2026-10-01" } }),
        null,
      ),
    ).toEqual(["android"]);
  });
});

describe("mergeBrands y parseBrands", () => {
  it("une sin repetir y en el orden de la lista", () => {
    expect(mergeBrands(["files", "garmin"], ["garmin", "apple"])).toEqual([
      "garmin",
      "apple",
      "files",
    ]);
  });

  it("ignora valores guardados no válidos", () => {
    expect(parseBrands('["apple","fitbit",3]')).toEqual(["apple"]);
    expect(parseBrands("no-json")).toEqual([]);
    expect(parseBrands(null)).toEqual([]);
  });
});
