import { describe, expect, it } from "vitest";

import type { Duel, FeedItem } from "@/types/api";

import {
  daysLeft,
  daysLeftText,
  duelLeader,
  duelOutcome,
  duelRecord,
  duelScore,
  duelShare,
  feedStats,
  followLabel,
  formatMetric,
  gapText,
  handleError,
  initials,
  normalizeHandle,
  patchFeed,
  profileUrl,
  rankChange,
  recordText,
  relativeDate,
  rivalOf,
  suggestHandle,
  toggledKudos,
} from "./social";

const ana = { user_id: 2, display_name: "Ana Pérez", handle: "ana" };
const yo = { user_id: 1, display_name: "Nico", handle: "nico" };

const duel = (over: Partial<Duel> = {}): Duel => ({
  id: 7,
  challenger: yo,
  opponent: ana,
  metric: "km",
  sport: "all",
  start_date: "2026-11-09",
  end_date: "2026-11-15",
  status: "active",
  my_value: 23.4,
  their_value: 21,
  winner_id: null,
  i_am_challenger: true,
  ...over,
});

const item = (over: Partial<FeedItem> = {}): FeedItem => ({
  activity_id: 1,
  owner: ana,
  sport: "running",
  name: "Rodaje",
  start_time: "2026-11-12T07:00:00Z",
  distance_m: 10000,
  duration_s: 3100,
  moving_duration_s: 3000,
  avg_speed: 10000 / 3000,
  elevation_gain_m: 85,
  is_race: false,
  track: null,
  achievements: [],
  kudos_count: 2,
  kudoed_by_me: false,
  comments_count: 0,
  mine: false,
  visibility: "followers",
  ...over,
});

describe("handle", () => {
  it("test_normalizar_cuando_lleva_arroba_y_mayusculas_entonces_limpio", () => {
    expect(normalizeHandle("  @Ana.Run ")).toBe("ana.run");
  });

  it("test_validar_cuando_formato_incorrecto_entonces_mensaje", () => {
    expect(handleError("ab")).toMatch(/al menos 3/);
    expect(handleError("a".repeat(31))).toMatch(/como mucho 30/);
    expect(handleError("ana-pérez")).toMatch(/Solo letras/);
    expect(handleError("Ana")).toMatch(/Solo letras/);
    expect(handleError("ana_run.88")).toBeNull();
  });

  it("test_sugerir_cuando_nombre_con_tildes_entonces_handle_valido", () => {
    expect(suggestHandle("Ana Pérez")).toBe("ana.perez");
    expect(suggestHandle("  José  María! ")).toBe("jose.maria");
    expect(handleError(suggestHandle("Íñigo Martínez de la Peña"))).toBeNull();
  });

  it("iniciales y enlace del perfil", () => {
    expect(initials("Ana Pérez García")).toBe("AG");
    expect(initials("nico")).toBe("N");
    expect(initials("  ")).toBe("?");
    expect(profileUrl("https://ktrain.app/", "ana")).toBe(
      "https://ktrain.app/u/ana",
    );
  });
});

describe("formatMetric", () => {
  it("test_formato_cuando_cada_metrica_entonces_su_unidad", () => {
    expect(formatMetric("km", 23.44)).toBe("23,4 km");
    expect(formatMetric("time", 3 * 3600 + 5 * 60)).toBe("3 h 05 min");
    expect(formatMetric("time", 45 * 60)).toBe("45 min");
    expect(formatMetric("elevation", 1230)).toBe("1230 m");
    expect(formatMetric("days", 1)).toBe("1 día");
    expect(formatMetric("days", 4)).toBe("4 días");
    expect(formatMetric("best_5k", 22 * 60 + 31)).toBe("22:31");
    expect(formatMetric("best_10k", null)).toBe("—");
  });
});

describe("clasificación", () => {
  it("test_diferencia_cuando_hay_alguien_delante_entonces_frase", () => {
    expect(gapText("km", 3.2, "Ana")).toBe("Te faltan 3,2 km para pasar a Ana");
    expect(gapText("time", 1800, "Ana")).toBe(
      "Te faltan 30 min para pasar a Ana",
    );
    expect(gapText("km", 0, "Ana")).toMatch(/empatado con Ana/);
    expect(gapText("km", null, null)).toBeNull();
  });

  it("test_cambio_de_puesto_cuando_sube_baja_o_nuevo_entonces_texto_e_icono", () => {
    expect(rankChange(1, 3)).toMatchObject({
      dir: "up",
      steps: 2,
      short: "↑2",
    });
    expect(rankChange(4, 3)).toMatchObject({
      dir: "down",
      label: "Baja 1 puesto",
    });
    expect(rankChange(2, 2).dir).toBe("same");
    expect(rankChange(2, null).short).toBe("Nuevo");
  });
});

describe("duelos", () => {
  it("test_lider_cuando_km_entonces_gana_el_mayor", () => {
    expect(duelLeader(duel())).toBe("me");
    expect(duelLeader(duel({ my_value: 5, their_value: 9 }))).toBe("them");
    expect(duelLeader(duel({ my_value: null, their_value: null }))).toBe("tie");
  });

  it("test_lider_cuando_mejor_marca_entonces_gana_el_menor_y_sin_marca_pierde", () => {
    const d = duel({ metric: "best_5k", my_value: 1300, their_value: 1260 });
    expect(duelLeader(d)).toBe("them");
    expect(duelLeader({ ...d, my_value: 1200 })).toBe("me");
    expect(duelLeader({ ...d, their_value: null })).toBe("me");
    expect(duelLeader({ ...d, my_value: null })).toBe("them");
  });

  it("test_barra_cuando_valores_entonces_parte_proporcional", () => {
    expect(duelShare(duel({ my_value: 30, their_value: 10 }))).toBeCloseTo(
      0.75,
    );
    expect(duelShare(duel({ my_value: null, their_value: null }))).toBe(0.5);
    // Mejor marca: más rápido = barra más larga.
    expect(
      duelShare(duel({ metric: "best_5k", my_value: 1000, their_value: 1500 })),
    ).toBeCloseTo(0.6);
  });

  it("marcador y rival según quién retó", () => {
    expect(duelScore(duel())).toBe("Tú 23,4 km · Ana 21,0 km");
    const recibido = duel({
      i_am_challenger: false,
      challenger: ana,
      opponent: yo,
    });
    expect(rivalOf(recibido).handle).toBe("ana");
  });

  it("test_resultado_cuando_terminado_entonces_victoria_derrota_o_empate", () => {
    expect(duelOutcome(duel())).toBeNull();
    expect(duelOutcome(duel({ status: "finished", winner_id: 1 }))).toBe("win");
    expect(duelOutcome(duel({ status: "finished", winner_id: 2 }))).toBe(
      "loss",
    );
    expect(duelOutcome(duel({ status: "finished", winner_id: null }))).toBe(
      "draw",
    );
    // Siendo el retado, el user_id propio es el del oponente.
    expect(
      duelOutcome(
        duel({
          status: "finished",
          winner_id: 1,
          i_am_challenger: false,
          challenger: ana,
          opponent: yo,
        }),
      ),
    ).toBe("win");
    const r = duelRecord([
      duel({ status: "finished", winner_id: 1 }),
      duel({ status: "finished", winner_id: 1 }),
      duel({ status: "finished", winner_id: 2 }),
      duel(),
    ]);
    expect(r).toEqual({ wins: 2, losses: 1, draws: 0 });
    expect(recordText(r)).toBe("2 victorias · 1 derrota · 0 empates");
  });

  it("test_dias_que_quedan_cuando_fechas_entonces_incluye_hoy", () => {
    expect(daysLeft("2026-11-15", "2026-11-13")).toBe(3);
    expect(daysLeft("2026-11-13", "2026-11-13")).toBe(1);
    expect(daysLeft("2026-11-12", "2026-11-13")).toBe(0);
    expect(daysLeftText(3)).toBe("Quedan 3 días");
    expect(daysLeftText(1)).toBe("Último día");
    expect(daysLeftText(0)).toBe("Terminado");
  });
});

describe("feed", () => {
  it("test_cifras_cuando_carrera_entonces_ritmo_y_bici_velocidad", () => {
    expect(feedStats(item()).map((s) => `${s.label}: ${s.value}`)).toEqual([
      "Distancia: 10,00 km",
      "Tiempo: 50:00",
      "Ritmo: 5:00 /km",
      "Desnivel: 85 m",
    ]);
    const bici = feedStats(item({ sport: "cycling", avg_speed: 8.5 }));
    expect(bici.find((s) => s.label === "Velocidad")?.value).toBe("30,6 km/h");
    // Ritmo oculto por la persona: no se inventa.
    expect(
      feedStats(item({ avg_speed: null })).map((s) => s.label),
    ).not.toContain("Ritmo");
  });

  it("fecha relativa", () => {
    const now = new Date("2026-11-13T12:00:00Z");
    expect(relativeDate("2026-11-13T11:59:30Z", now)).toBe("ahora");
    expect(relativeDate("2026-11-13T11:40:00Z", now)).toBe("hace 20 min");
    expect(relativeDate("2026-11-13T09:00:00Z", now)).toBe("hace 3 h");
    expect(relativeDate("2026-11-10T09:00:00Z", now)).toBe("hace 3 días");
    expect(relativeDate("2026-10-01T09:00:00Z", now)).toBe("01/10/2026");
  });

  it("test_kudos_optimistas_cuando_toco_entonces_alterna_y_ajusta_contador", () => {
    expect(toggledKudos({ kudos_count: 2, kudoed_by_me: false })).toEqual({
      kudos_count: 3,
      kudoed_by_me: true,
    });
    expect(
      toggledKudos({ kudos_count: 0, kudoed_by_me: true }).kudos_count,
    ).toBe(0);
    const data = {
      pages: [{ items: [item(), item({ activity_id: 2 })], next_before: null }],
      pageParams: [null],
    };
    const out = patchFeed(data, 2, toggledKudos)!;
    expect(out.pages[0].items[1].kudos_count).toBe(3);
    expect(out.pages[0].items[0]).toBe(data.pages[0].items[0]);
    expect(patchFeed(undefined, 1, toggledKudos)).toBeUndefined();
  });

  it("botón de seguir", () => {
    expect(followLabel("none")).toBe("Seguir");
    expect(followLabel("pending")).toBe("Pendiente");
    expect(followLabel("accepted")).toBe("Siguiendo");
  });
});
