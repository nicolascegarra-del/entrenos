import { describe, expect, it } from "vitest";

import type { AiProviders, GarminStatus } from "@/types/api";

import { settingsStatus } from "./settings-sections";

const garmin = (
  status: "none" | "ok" | "expired",
  name: string | null = null,
) =>
  ({
    connected: status === "ok",
    connection: {
      status,
      display_name: name,
      connected_at: null,
      last_ok_at: null,
    },
    last_run: null,
  }) as GarminStatus;

describe("settingsStatus", () => {
  it("estado de la conexión, con aviso si hace falta", () => {
    expect(settingsStatus({ garmin: garmin("ok", "Nico") }).conexiones).toEqual(
      {
        text: "Garmin conectado (Nico)",
      },
    );
    expect(settingsStatus({ garmin: garmin("expired") }).conexiones?.warn).toBe(
      true,
    );
  });

  it("asistente predeterminado y notificaciones", () => {
    const ai = {
      daily_limit: 100,
      used_today: 0,
      providers: [
        {
          label: "Claude (Anthropic)",
          configured: true,
          enabled: true,
          is_default: true,
          model: "claude-haiku-5-5",
          default_model: "x",
        },
      ],
    } as unknown as AiProviders;
    expect(settingsStatus({ ai }).asistente?.text).toBe(
      "Claude · claude-haiku-5-5",
    );
    expect(
      settingsStatus({ notifications: { devices: [] } as never }).notificaciones
        ?.text,
    ).toBe("Desactivadas");
  });
});
