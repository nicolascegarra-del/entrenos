import { describe, expect, it } from "vitest";

import { askAboutActivity } from "@/components/activity/ask-ai";

import { consultedSummary } from "./consulted";

describe("asistente", () => {
  it("resumen de consultas en singular y plural", () => {
    expect(consultedSummary(1)).toBe("Ha consultado 1 dato");
    expect(consultedSummary(3)).toBe("Ha consultado 3 datos");
  });

  it("pregunta preparada con el id de la actividad", () => {
    const q = askAboutActivity({
      id: 52,
      name: "Series",
      start_time: "2026-10-13T17:33:00Z",
    });
    expect(q).toContain("(id 52)");
    expect(q).toContain("«Series» del 13/10/2026");
  });
});
