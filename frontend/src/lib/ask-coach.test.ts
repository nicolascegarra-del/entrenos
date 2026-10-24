import { describe, expect, it } from "vitest";

import { askAboutSession, askCoachHref, todaySuggestions } from "./ask-coach";

const readiness = (status: "good" | "watch" | "alert" | "nodata") => ({
  status,
  title: "",
  message: "",
  acwr: null,
});
const session = (day: string, activity_id: number | null = null) => ({
  id: 7,
  day,
  title: "Series 6x1000",
  sport: "running",
  compliance_score: null,
  activity_id,
});

describe("ask-coach", () => {
  it("el enlace envía la pregunta al abrir el chat", () => {
    expect(askCoachHref("¿Qué tal?")).toBe(
      "/asistente?q=%C2%BFQu%C3%A9%20tal%3F&auto=1",
    );
  });

  it("la pregunta de una sesión lleva su id", () => {
    expect(
      askAboutSession({ id: 7, day: "2026-10-24", title: "Rodaje" }),
    ).toContain("(id 7)");
  });

  it("sugerencias según el día", () => {
    expect(
      todaySuggestions(
        {
          readiness: readiness("alert"),
          planned_this_week: [session("2026-10-24")],
        },
        "2026-10-24",
      ),
    ).toEqual([
      "¿Entreno hoy o mejor descanso?",
      "¿Cómo hago hoy «Series 6x1000»?",
      "¿Qué tal voy esta semana?",
    ]);
    // Sesión ya hecha o de otro día: no se sugiere.
    expect(
      todaySuggestions(
        {
          readiness: readiness("good"),
          planned_this_week: [session("2026-10-24", 3), session("2026-10-25")],
        },
        "2026-10-24",
      ),
    ).toEqual(["¿Qué tal voy esta semana?", "¿Qué me toca los próximos días?"]);
  });
});
