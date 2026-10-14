import { describe, expect, it } from "vitest";

import { formatDistance, formatDuration, formatPace, speedToPace, sportInfo } from "@/lib/format";

describe("format", () => {
  it("formatDuration cuando menos de una hora entonces m:ss", () => {
    expect(formatDuration(255)).toBe("4:15");
    expect(formatDuration(3725)).toBe("1:02:05");
    expect(formatDuration(null)).toBe("—");
  });

  it("formatDistance cuando km entonces dos decimales con coma", () => {
    expect(formatDistance(6009.75)).toBe("6,01 km");
    expect(formatDistance(850)).toBe("850 m");
  });

  it("speedToPace cuando parado entonces null para no dibujar picos", () => {
    expect(speedToPace(0.2)).toBeNull();
    expect(speedToPace(4)).toBe(250);
    expect(formatPace(4)).toBe("4:10 /km");
  });

  it("sportInfo cuando deporte desconocido entonces etiqueta legible", () => {
    expect(sportInfo("running").pace).toBe(true);
    expect(sportInfo("stand_up_paddleboarding").label).toBe("stand up paddleboarding");
  });
});
