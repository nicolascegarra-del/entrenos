import { describe, expect, it } from "vitest";

import type {
  HealthDay,
  HealthNight,
  HeartRateSample,
  OuraStatus,
  RestPeriod,
} from "@/types/api";

import {
  activityRuns,
  contributorList,
  dayHasData,
  decodeRuns,
  formatHm,
  formatTempDelta,
  heartRateByOrigin,
  historyText,
  hourTicks,
  hrOrigin,
  hypnogramRuns,
  isIsoDay,
  lowBattery,
  mergeByDay,
  seriesAverages,
  toShares,
  nightHasData,
  offsetClock,
  ouraCardState,
  phaseTotals,
  recoveryFromOura,
  resilienceLabel,
  resilienceLevelName,
  restDays,
  restPeriodOn,
  ringSummary,
  seriesPoints,
  shiftDay,
  showSourcePicker,
  sleepTimeText,
} from "./oura";

/** Payload de ejemplo de `GET /api/v1/sources/oura` (contrato). */
const status = (patch: Partial<OuraStatus> = {}): OuraStatus => ({
  configured: true,
  connected: true,
  status: "ok",
  last_sync_at: "2026-10-28T06:30:00Z",
  last_error: "",
  scopes: ["daily", "heartrate", "personal"],
  ring: {
    model: "gen3_heritage",
    color: "stealth_black",
    size: 9,
    firmware: "2.9.21",
    battery_level: 62,
    battery_at: "2026-10-28T06:00:00Z",
  },
  recovery_source: "auto",
  has_watch: false,
  history: { status: "idle", from: null, to: null },
  ...patch,
});

/** Payload de ejemplo de `GET /api/v1/health/night/2026-10-28`. */
const night: HealthNight = {
  day: "2026-10-28",
  source: "oura",
  main: {
    type: "long_sleep",
    bedtime_start: "2026-10-27T23:00:00Z",
    bedtime_end: "2026-10-28T06:30:00Z",
    total_sleep_s: 25200,
    deep_s: 5400,
    rem_s: 6300,
    light_s: 13500,
    awake_s: 1800,
    latency_s: 600,
    efficiency: 93,
    time_in_bed_s: 27000,
    avg_hr: 52,
    lowest_hr: 46,
    avg_hrv: 61,
    avg_breath: 14.5,
    restless_periods: 180,
  },
  naps: [],
  hypnogram: {
    start: "2026-10-27T23:00:00Z",
    interval_s: 300,
    phases: "44221113324",
  },
  hr: {
    start: "2026-10-27T23:00:00Z",
    interval_s: 300,
    items: [58, null, 54, 0, 50],
  },
  hrv: { start: "2026-10-27T23:00:00Z", interval_s: 300, items: [40, 55] },
  sleep_score: 84,
  sleep_contributors: {
    total_sleep: 90,
    deep_sleep: 99,
    latency: 80,
    efficiency: null,
    nuevo_contribuidor: 120,
  },
  readiness: {
    score: 78,
    temperature_deviation: -0.12,
    temperature_trend_deviation: 0.05,
    contributors: { hrv_balance: 70, previous_night: 85 },
  },
  sleep_time: {
    recommendation: "earlier_bedtime",
    status: "optimal_found",
    optimal_bedtime: { start_offset: -3600, end_offset: 1800, day_tz: 3600 },
  },
  spo2: { average: 97.4, breathing_disturbance_index: 3 },
  tags: [],
};

/** Payload de ejemplo de `GET /api/v1/health/day/2026-10-28`. */
const day: HealthDay = {
  day: "2026-10-28",
  heartrate: [],
  activity: {
    score: 81,
    steps: 9500,
    active_calories: 420,
    total_calories: 2450,
    high_s: 900,
    medium_s: 2400,
    low_s: 10800,
    sedentary_s: 30000,
    non_wear_s: 600,
    class_5min: { start: "2026-10-28T04:00:00Z", classes: "0011x345" },
    met: { start: "2026-10-28T04:00:00Z", interval_s: 60, items: [0.9, 1.2] },
  },
  stress: { stress_high_s: 3600, recovery_high_s: 5400, day_summary: "normal" },
  resilience: { level: "solid", contributors: { sleep_recovery: 70 } },
  sessions: [],
  tags: [],
  rest_mode: null,
};

const T = (iso: string) => new Date(iso).getTime();

describe("ouraCardState", () => {
  it("test_estado_cuando_no_hay_credenciales_entonces_pendiente_de_configurar", () => {
    expect(ouraCardState(status({ configured: false, connected: false }))).toBe(
      "unconfigured",
    );
  });
  it("cuando caduca el token, entonces pide volver a conectar aunque venga desconectado", () => {
    expect(ouraCardState(status({ status: "expired" }))).toBe("expired");
    expect(ouraCardState(status({ status: "expired", connected: false }))).toBe(
      "expired",
    );
  });
  it("conectado y desconectado", () => {
    expect(ouraCardState(status())).toBe("connected");
    expect(ouraCardState(status({ connected: false, status: null }))).toBe(
      "disconnected",
    );
  });
});

describe("selector de fuente y batería", () => {
  it("el selector solo sale con reloj y anillo conectados", () => {
    expect(showSourcePicker(undefined)).toBe(false);
    expect(showSourcePicker(status())).toBe(false);
    expect(showSourcePicker(status({ has_watch: true }))).toBe(true);
    expect(
      showSourcePicker(status({ has_watch: true, connected: false })),
    ).toBe(false);
  });
  it("batería baja por debajo del 15 %, sin dato no avisa", () => {
    expect(lowBattery(status().ring)).toBe(false);
    expect(lowBattery({ ...status().ring!, battery_level: 14 })).toBe(true);
    expect(lowBattery({ ...status().ring!, battery_level: 15 })).toBe(false);
    expect(lowBattery({ ...status().ring!, battery_level: null })).toBe(false);
    expect(lowBattery(null)).toBe(false);
  });
  it("resumen del anillo legible", () => {
    expect(ringSummary(status().ring)).toBe(
      "Gen3 heritage · talla 9 · Stealth black",
    );
    expect(ringSummary(null)).toBeNull();
  });
});

describe("recoveryFromOura", () => {
  it("manda la elección; en automático, la fuente de la noche", () => {
    expect(recoveryFromOura(undefined, "oura")).toBe(false);
    expect(
      recoveryFromOura(status({ recovery_source: "oura" }), "garmin"),
    ).toBe(true);
    expect(recoveryFromOura(status({ recovery_source: "watch" }), "oura")).toBe(
      false,
    );
    expect(recoveryFromOura(status({ has_watch: true }), "oura")).toBe(true);
    expect(recoveryFromOura(status({ has_watch: true }), "garmin")).toBe(false);
  });
  it("en automático sin noche: Oura si no hay reloj", () => {
    expect(recoveryFromOura(status(), null)).toBe(true);
    expect(recoveryFromOura(status({ has_watch: true }), null)).toBe(false);
    expect(recoveryFromOura(status({ connected: false }), "oura")).toBe(false);
  });
});

describe("historyText", () => {
  it("cuenta la importación según su estado", () => {
    expect(historyText({ status: "idle", from: null, to: null })).toBeNull();
    expect(
      historyText({ status: "running", from: "2024-01-01", to: "2026-10-28" }),
    ).toMatch(/^Importando tu histórico del 1 ene/);
    expect(
      historyText({ status: "done", from: "2024-01-01", to: null }),
    ).toMatch(/^Histórico importado desde el 1 ene/);
    expect(historyText({ status: "error", from: null, to: null })).toMatch(
      /No se pudo/,
    );
  });
});

describe("formatos", () => {
  it("formatHm", () => {
    expect(formatHm(25200)).toBe("7 h");
    expect(formatHm(27120)).toBe("7 h 32 min");
    expect(formatHm(600)).toBe("10 min");
    expect(formatHm(null)).toBe("—");
  });
  it("offsetClock: segundos desde la medianoche, negativos antes", () => {
    expect(offsetClock(-3600)).toBe("23:00");
    expect(offsetClock(1800)).toBe("00:30");
    expect(offsetClock(0)).toBe("00:00");
  });
  it("temperatura con signo", () => {
    expect(formatTempDelta(-0.12)).toBe("−0,12 °C");
    expect(formatTempDelta(0.3)).toBe("+0,3 °C");
    expect(formatTempDelta(null)).toBe("—");
  });
  it("días: desplazar y validar", () => {
    expect(shiftDay("2026-10-31", 1)).toBe("2026-11-01");
    expect(shiftDay("2026-03-01", -1)).toBe("2026-02-28");
    expect(isIsoDay("2026-10-28")).toBe(true);
    expect(isIsoDay("2026-02-30")).toBe(false);
    expect(isIsoDay("hoy")).toBe(false);
  });
  it("horas en punto dentro del rango", () => {
    const start = new Date(2026, 9, 27, 23, 10).getTime();
    const end = new Date(2026, 9, 28, 2, 0).getTime();
    expect(hourTicks(start, end).map((t) => new Date(t).getHours())).toEqual([
      0, 1, 2,
    ]);
  });
});

describe("hipnograma", () => {
  it("decodifica tramos con su hora de inicio y fin", () => {
    const runs = hypnogramRuns(night.hypnogram);
    expect(runs.map((r) => r.phase)).toEqual([
      "awake",
      "light",
      "deep",
      "rem",
      "light",
      "awake",
    ]);
    expect(runs[0]).toEqual({
      phase: "awake",
      start: T("2026-10-27T23:00:00Z"),
      end: T("2026-10-27T23:10:00Z"),
    });
    expect(runs[2].end - runs[2].start).toBe(15 * 60_000);
    expect(runs[runs.length - 1].end).toBe(T("2026-10-27T23:55:00Z"));
  });
  it("suma el tiempo por fase e ignora caracteres desconocidos", () => {
    const runs = hypnogramRuns({ ...night.hypnogram!, phases: "11x4" });
    expect(phaseTotals(runs)).toEqual({
      deep: 600,
      light: 0,
      rem: 0,
      awake: 300,
    });
    expect(hypnogramRuns(null)).toEqual([]);
  });
  it("decodeRuns sin inicio válido no inventa tramos", () => {
    expect(decodeRuns("no-es-fecha", 300, "111")).toEqual([]);
  });
});

describe("series", () => {
  it("los ceros y huecos cortan la línea", () => {
    const pts = seriesPoints(night.hr);
    expect(pts.map((p) => p.value)).toEqual([58, null, 54, null, 50]);
    expect(pts[2].t - pts[0].t).toBe(600_000);
    expect(seriesPoints(null)).toEqual([]);
  });
  it("mergeByDay une series por día con huecos a null", () => {
    expect(
      mergeByDay(
        {
          deep: [
            { day: "2026-10-27", value: 3600 },
            { day: "2026-10-28", value: 7200 },
          ],
          rem: [{ day: "2026-10-28", value: 3600 }],
        },
        (v) => v / 3600,
      ),
    ).toEqual([
      { day: "2026-10-27", deep: 1, rem: null },
      { day: "2026-10-28", deep: 2, rem: 1 },
    ]);
  });
});

describe("FC del día por origen", () => {
  it("agrupa por origen y reduce a una muestra por minuto", () => {
    const base = T("2026-10-28T08:00:00Z") / 1000;
    const samples: HeartRateSample[] = [
      [base, 60, "awake"],
      [base + 10, 70, "workout"],
      [base + 20, 80, "workout"],
      [base + 70, 90, "workout"],
      [base + 120, 50, "rest"],
      [base + 180, 48, "sleep"],
      [base + 240, 65, "live"],
      [base + 300, 0, "awake"],
      [base + 360, 62, "algo_nuevo"],
    ];
    const g = heartRateByOrigin(samples);
    expect(g.workout).toEqual([
      { t: base * 1000, bpm: 75 },
      { t: (base + 60) * 1000, bpm: 90 },
    ]);
    expect(g.awake.map((p) => p.bpm)).toEqual([60, 62]);
    expect(g.session.map((p) => p.bpm)).toEqual([65]);
    expect(g.rest).toHaveLength(1);
    expect(g.sleep).toHaveLength(1);
  });
  it("hrOrigin manda lo desconocido a despierto", () => {
    expect(hrOrigin("live")).toBe("session");
    expect(hrOrigin("x")).toBe("awake");
  });
});

describe("actividad cada 5 min", () => {
  it("decodifica las clases e ignora caracteres desconocidos", () => {
    const runs = activityRuns(day.activity!.class_5min);
    expect(runs.map((r) => r.code)).toEqual(["0", "1", "3", "4", "5"]);
    expect(runs[1].end - runs[1].start).toBe(10 * 60_000);
    expect(activityRuns(null)).toEqual([]);
  });
});

describe("modo descanso", () => {
  const periods: RestPeriod[] = [
    { start_date: "2026-10-20", end_date: "2026-10-22", source: "oura" },
    { start_date: "2026-10-27", end_date: null, source: "oura" },
  ];
  it("incluye los extremos y un periodo sin fin sigue activo", () => {
    expect(restPeriodOn(periods, "2026-10-20")).toBe(periods[0]);
    expect(restPeriodOn(periods, "2026-10-22")).toBe(periods[0]);
    expect(restPeriodOn(periods, "2026-10-23")).toBeNull();
    expect(restPeriodOn(periods, "2026-11-30")).toBe(periods[1]);
    expect(restPeriodOn(undefined, "2026-10-20")).toBeNull();
  });
  it("restDays marca solo los días que caen dentro", () => {
    expect([
      ...restDays(periods, ["2026-10-21", "2026-10-24", "2026-10-27"]),
    ]).toEqual(["2026-10-21", "2026-10-27"]);
  });
});

describe("contribuidores y textos", () => {
  it("ordena, quita nulos, recorta a 0–100 y nombra los desconocidos", () => {
    expect(contributorList(night.sleep_contributors, "sleep")).toEqual([
      { key: "total_sleep", label: "Sueño total", value: 90 },
      { key: "deep_sleep", label: "Sueño profundo", value: 99 },
      { key: "latency", label: "Latencia", value: 80 },
      { key: "nuevo_contribuidor", label: "Nuevo contribuidor", value: 100 },
    ]);
    expect(
      contributorList(night.readiness!.contributors, "readiness").map(
        (c) => c.key,
      ),
    ).toEqual(["previous_night", "hrv_balance"]);
    expect(contributorList(null, "sleep")).toEqual([]);
  });
  it("resiliencia", () => {
    expect(resilienceLabel(day.resilience!.level)).toBe("Sólida");
    expect(resilienceLevelName(1)).toBe("Limitada");
    expect(resilienceLevelName(5)).toBe("Excepcional");
  });
  it("horario recomendado", () => {
    expect(sleepTimeText(night.sleep_time)).toEqual({
      window: "Entre las 23:00 y las 00:30",
      status: "Tu horario ideal para acostarte.",
      recommendation: "Prueba a acostarte antes.",
    });
    expect(sleepTimeText(null)).toBeNull();
    expect(
      sleepTimeText({
        recommendation: null,
        status: null,
        optimal_bedtime: null,
      }),
    ).toBeNull();
  });
  it("hay datos de la noche y del día", () => {
    expect(nightHasData(night)).toBe(true);
    expect(
      nightHasData({
        ...night,
        main: null,
        hypnogram: null,
        sleep_score: null,
        readiness: null,
        spo2: null,
      }),
    ).toBe(false);
    expect(dayHasData(day)).toBe(true);
    expect(
      dayHasData({
        ...day,
        activity: null,
        stress: null,
        resilience: null,
      }),
    ).toBe(false);
  });
});

describe("partes de un total", () => {
  const rows = [
    { day: "2026-10-01", deep: 1.5, rem: 1.5, light: 3 },
    { day: "2026-10-02", deep: 1, rem: null, light: 3 },
  ];

  it("toShares pasa cada día a % de su total", () => {
    const [a, b] = toShares(rows, ["deep", "rem", "light"]);
    expect(a.deep).toBe(25);
    expect(a.light).toBe(50);
    expect(b.deep).toBe(25);
    expect(b.rem).toBeNull();
  });

  it("seriesAverages da la media de cada parte y su %", () => {
    const avgs = seriesAverages(rows, ["deep", "rem", "light"]);
    expect(avgs.map((a) => a.avg)).toEqual([1.25, 1.5, 3]);
    expect(Math.round(avgs[2].share!)).toBe(52);
  });
});
