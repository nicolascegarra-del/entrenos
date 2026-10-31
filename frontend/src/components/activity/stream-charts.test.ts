import { describe, expect, it } from "vitest";

import { chartChannels } from "./stream-charts";

describe("chartChannels", () => {
  it("cuando la actividad trae FC y MET (Oura) entonces pide ambas series y el tiempo", () => {
    expect(chartChannels(["met", "hr", "time"])).toEqual(["time", "hr", "met"]);
  });

  it("cuando hay canales desconocidos entonces los ignora", () => {
    expect(chartChannels(["lat", "lon", "speed", "distance"])).toEqual([
      "distance",
      "speed",
    ]);
  });
});
