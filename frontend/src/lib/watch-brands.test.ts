import { describe, expect, it } from "vitest";

import type {
  DevicesStatus,
  GarminStatus,
  OuraStatus,
  SourcesStatus,
} from "@/types/api";

import {
  connectedBrands,
  connectedDevices,
  mergeBrands,
  otherWatch,
  parseBrands,
} from "./watch-brands";

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
  it("marca Oura conectado o caducado", () => {
    const oura = (connected: boolean, status: "ok" | "expired" | null) =>
      ({ connected, status }) as OuraStatus;
    expect(
      connectedBrands(undefined, sources(), null, oura(true, "ok")),
    ).toEqual(["oura"]);
    expect(
      connectedBrands(undefined, sources(), null, oura(false, "expired")),
    ).toEqual(["oura"]);
    expect(
      connectedBrands(undefined, sources(), null, oura(false, null)),
    ).toEqual([]);
  });

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

const devices = (
  ...rows: [DevicesStatus["connections"][number]["provider"], string][]
): DevicesStatus => ({
  enabled: ["suunto", "zepp", "xiaomi"],
  connections: rows.map(([provider, status]) => ({
    provider,
    label: provider,
    account: "yo",
    status: status as "ok",
    last_sync_at: null,
    last_error: "",
  })),
});

const ouraOk = { connected: true, status: "ok" } as OuraStatus;

describe("connectedDevices", () => {
  it("cuando no hay nada, entonces «Ningún dispositivo conectado»", () => {
    expect(
      connectedDevices({ garmin: garmin(false, "none"), sources: sources() })
        .label,
    ).toBe("Ningún dispositivo conectado");
  });

  it("cuando solo hay Oura, entonces lo cuenta y no habla de Garmin", () => {
    const r = connectedDevices({
      garmin: garmin(false, "none"),
      sources: sources(),
      oura: ouraOk,
    });
    expect(r.label).toBe("1 dispositivo conectado: Oura");
    expect(r.broken).toEqual([]);
  });

  it("cuando hay varios, entonces los enumera en orden", () => {
    const r = connectedDevices({
      garmin: garmin(true, "ok"),
      sources: sources(),
      oura: ouraOk,
      devices: devices(["suunto", "ok"], ["xiaomi", "pending"]),
    });
    expect(r.label).toBe("3 dispositivos conectados: Garmin, Suunto, Oura");
  });

  it("cuando una conexión caduca, entonces va a `broken` y no cuenta", () => {
    const r = connectedDevices({
      garmin: garmin(false, "expired"),
      sources: sources(),
      devices: devices(["zepp", "ok"]),
    });
    expect(r.connected).toEqual(["Amazfit"]);
    expect(r.broken).toEqual(["Garmin"]);
  });
});

describe("otherWatch y connectedBrands con marcas por cuenta", () => {
  it("cuenta Suunto como reloj y marca su casilla", () => {
    expect(otherWatch(sources(), devices(["suunto", "ok"]))).toBe("Suunto");
    expect(
      connectedBrands(
        garmin(false, "none"),
        sources(),
        null,
        undefined,
        devices(["suunto", "ok"], ["xiaomi", "pending"]),
      ),
    ).toEqual(["suunto"]);
  });
});
