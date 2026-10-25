import pytest

from app.services import nutrition as nu
from app.services import race_day as rd

# ─── Gasto basal y carga del día ─────────────────────────────────────────────


def test_bmr_cuando_mujer_60kg_entonces_mifflin_st_jeor():
    assert nu.bmr("mujer", 60, 165, 30) == pytest.approx(1320.25, abs=0.1)


def test_bmr_cuando_hombre_80kg_entonces_mifflin_st_jeor():
    assert nu.bmr("hombre", 80, 180, 35) == pytest.approx(1755.0)


def test_bmr_cuando_hay_masa_magra_entonces_cunningham():
    assert nu.bmr("hombre", 80, 180, 35, lean_mass_kg=65) == pytest.approx(1930.0)


@pytest.mark.parametrize(
    ("minutes", "intensity", "level"),
    [(0, "moderada", "descanso"), (40, "moderada", "ligero"), (60, "moderada", "moderado"),
     (120, "suave", "moderado"), (120, "moderada", "alto"), (180, "alta", "alto"), (300, "moderada", "muy_alto"),
     (40, "alta", "moderado")],
)  # fmt: skip
def test_day_load_level_cuando_duracion_e_intensidad_entonces_nivel(minutes, intensity, level):
    assert nu.day_load_level(minutes, intensity) == level


def test_exercise_kcal_cuando_1h_moderada_80kg_entonces_met_neto():
    assert nu.exercise_kcal(60, 80, "moderate") == pytest.approx(8.8 * 80)


# ─── Objetivos diarios ───────────────────────────────────────────────────────


def test_daily_targets_cuando_60kg_1h_moderada_entonces_rangos_de_referencia():
    t = nu.daily_targets("mujer", 60, 165, 30, planned_minutes=60, intensity="moderada")
    assert t.load == "moderado" and t.exercise_source == "estimado"
    assert (t.carbs_g.low, t.carbs_g.high, t.carbs_g.recommended) == (300, 420, 360)
    assert (t.protein_g.low, t.protein_g.high, t.protein_g.recommended) == (72, 120, 96)
    assert t.protein_per_meal_g == 18 and t.meals == 4
    assert t.kcal.recommended == 2376 and t.kcal.low < t.kcal.recommended < t.kcal.high
    assert t.fat_pct >= 20 and t.fat_g.low <= t.fat_g.recommended <= t.fat_g.high
    assert t.disclaimer == nu.DISCLAIMER and any("Mifflin" in r for r in t.references)


def test_daily_targets_cuando_80kg_2h_entonces_carga_alta():
    t = nu.daily_targets("hombre", 80, 180, 35, planned_minutes=120)
    assert t.load == "alto"
    assert (t.carbs_g.low, t.carbs_g.high, t.carbs_g.recommended) == (480, 800, 640)
    assert t.exercise_kcal == pytest.approx(1408)
    assert t.kcal.recommended == 3865 and t.fat_pct >= 20


def test_daily_targets_cuando_hay_kcal_reales_entonces_las_usa_sin_el_basal():
    t = nu.daily_targets("hombre", 80, 180, 35, planned_minutes=60, actual_kcal=900)
    assert t.exercise_source == "actividad"
    assert t.exercise_kcal == pytest.approx(900 - 1755 * 60 / 1440, abs=0.1)


def test_daily_targets_cuando_descanso_entonces_hidratos_bajos_y_sin_gasto():
    t = nu.daily_targets("mujer", 60, 165, 30)
    assert t.load == "descanso" and t.exercise_kcal == 0 and t.exercise_source == "ninguno"
    assert t.carbs_g_kg.low == 3 and t.carbs_g.recommended == 180


def test_daily_targets_cuando_macros_no_caben_entonces_sube_energia_y_grasa_20():
    t = nu.daily_targets("mujer", 60, 165, 30, planned_minutes=300, actual_kcal=0)
    assert t.load == "muy_alto" and t.fat_pct == pytest.approx(20, abs=0.2)
    assert t.kcal.recommended == round((600 * 4 + 96 * 4) / 0.8) and t.notes


def test_daily_targets_cuando_masa_magra_entonces_cita_cunningham():
    t = nu.daily_targets("hombre", 80, 180, 35, lean_mass_kg=65)
    assert t.bmr_kcal == 1930 and any("Cunningham" in r for r in t.references)


# ─── Durante la sesión ───────────────────────────────────────────────────────


def test_during_session_cuando_40_min_entonces_nada():
    d = nu.during_session(40)
    assert d.band == "nada" and d.units == 0 and d.carbs_g_h.high == 0 and d.interval_min is None


def test_during_session_cuando_1h_entonces_enjuague_sin_geles():
    d = nu.during_session(60)
    assert d.band == "enjuague" and d.units == 0 and d.carbs_g_h.recommended == 0 and "enjuague" in d.text


def test_during_session_cuando_2h_moderada_entonces_30_60_y_dos_geles():
    d = nu.during_session(120, "moderada")
    assert d.band == "30-60" and d.carbs_g_h.recommended == 45 and d.first_intake_min == 40
    assert d.total_carbs_g == 60 and d.units == 2 and d.interval_min == 40
    assert d.text.startswith("≈ 2 geles de 25 g") and not d.multiple_transportable


def test_during_session_cuando_3h_alta_entonces_hasta_90_glucosa_fructosa():
    d = nu.during_session(180, "alta")
    assert d.band == "hasta-90" and d.carbs_g_h.recommended == 90 and d.multiple_transportable
    assert d.units == 9 and d.first_intake_min == 30 and "fructosa" in d.text


def test_during_session_cuando_producto_de_40g_entonces_pauta_en_barritas():
    d = nu.during_session(120, "moderada", product_carbs_g=40, product="barrita")
    assert d.units == 2 and "barritas de 40 g" in d.text


def test_race_day_cuando_misma_duracion_entonces_mismas_bandas_que_nutricion():
    for minutes in (40, 60, 95, 150, 210):
        band = nu.carbs_band(minutes)
        f = rd.fueling(minutes * 60, 18)
        assert f["carbs_g_h"] == [band.low, band.high] and f["note"] == band.note
        assert f["fluid_ml_h"] == list(nu.fluid_ml_h(18))
    assert rd.fueling(60 * 60, 18)["gels"] == 0


# ─── Hidratación ─────────────────────────────────────────────────────────────


def test_hydration_cuando_pierde_2_por_ciento_entonces_fuera_de_objetivo():
    h = nu.hydration(70, 68.6, 0.5, 1)
    assert h.sweat_l == pytest.approx(1.9) and h.sweat_rate_l_h == pytest.approx(1.9)
    assert h.loss_pct == pytest.approx(2.0) and not h.within_target
    assert h.drink_to_stay_under_2pct_ml_h == 500
    assert (h.rehydrate_l.low, h.rehydrate_l.high) == (1.75, 2.1)
    assert (h.sodium_mg_h.low, h.sodium_mg_h.high) == (300, 600)


def test_hydration_cuando_pierde_poco_entonces_dentro_de_objetivo():
    h = nu.hydration(70, 69.5, 0.5, 1)
    assert h.within_target and h.sweat_l == pytest.approx(1.0) and h.drink_to_stay_under_2pct_ml_h == 0


def test_hydration_cuando_gana_peso_entonces_aviso_hiponatremia():
    h = nu.hydration(70, 70.4, 1.5, 1.5)
    assert h.weight_gain and not h.within_target and "hiponatremia" in h.text


# ─── Carrera ─────────────────────────────────────────────────────────────────


def test_race_plan_cuando_10k_en_45_min_entonces_sin_carga_de_hidratos():
    p = nu.race_plan(10_000, 45 * 60, 60)
    assert p.carb_loading is None and p.during.units == 0 and p.feed_points == []


def test_race_plan_cuando_media_en_95_min_entonces_carga_10_12_g_kg():
    p = nu.race_plan(21_097, 95 * 60, 60)
    assert (p.carb_loading.low, p.carb_loading.high) == (600, 720)
    assert p.carb_loading_g_kg.low == 10 and p.feed_points


def test_race_plan_cuando_maraton_entonces_cafeina_comida_previa_y_tomas_por_km():
    p = nu.race_plan(42_195, 3.5 * 3600, 70)
    assert (p.caffeine_mg.low, p.caffeine_mg.high) == (210, 420) and "Pruébala" in p.caffeine_note
    assert (p.pre_meal_g.low, p.pre_meal_g.high) == (70, 280) and p.pre_meal_hours == (1, 4)
    assert p.during.carbs_g_h.recommended == 90 and len(p.feed_points) == 11
    assert p.feed_points[0].time_min == 30 and p.feed_points[0].km == pytest.approx(6.0)
    assert all(a.km < b.km for a, b in zip(p.feed_points, p.feed_points[1:], strict=False))


def test_race_plan_cuando_toma_cae_en_subida_entonces_se_adelanta_al_pie():
    profile = [[0, 100], [5000, 100], [7000, 300], [20000, 300]]
    p = nu.race_plan(20_000, 120 * 60, 70, profile=profile)
    first = p.feed_points[0]
    assert first.km == pytest.approx(5.0) and first.note == "antes de la subida" and first.time_min == 29
    flat = nu.race_plan(20_000, 120 * 60, 70)
    assert flat.feed_points[0].time_min == 40 and flat.feed_points[0].note == ""


def test_race_plan_cuando_perfil_invalido_entonces_value_error():
    with pytest.raises(ValueError):
        nu.race_plan(20_000, 7200, 70, profile=[[1000, 10], [500, 20]])


# ─── Recuperación y RED-S ────────────────────────────────────────────────────


def test_recovery_cuando_siguiente_sesion_en_4h_entonces_hidratos_por_hora():
    r = nu.recovery(4, 60)
    assert r.quick and (r.carbs_g_h.low, r.carbs_g_h.high) == (60, 72) and r.protein_g == 18 and r.carbs_hours == 4


def test_recovery_cuando_siguiente_sesion_en_24h_entonces_comidas_normales():
    r = nu.recovery(24, 80)
    assert not r.quick and r.carbs_g_h is None and r.protein_g == 24


def test_energy_availability_cuando_menos_de_30_entonces_aviso_red_s_sin_cifras():
    ea = nu.energy_availability(2000, 800, 50)
    assert ea.kcal_per_kg_ffm == 24 and ea.level == "baja" and ea.red_s_risk
    assert "dietista" in ea.text and not any(ch.isdigit() for ch in ea.text)


@pytest.mark.parametrize(("intake", "level"), [(2800, "reducida"), (3200, "optima")])
def test_energy_availability_cuando_suficiente_entonces_sin_riesgo(intake, level):
    ea = nu.energy_availability(intake, 800, 50)
    assert ea.level == level and not ea.red_s_risk


# ─── Seguridad ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kwargs",
    [{"age": 16}, {"age": 30, "pregnant": True}, {"age": 30, "eating_disorder_history": True},
     {"age": 30, "conditions": ["diabetes tipo 1"]}],
)  # fmt: skip
def test_safety_flags_cuando_caso_sensible_entonces_sin_perdida_de_peso_ni_menus(kwargs):
    f = nu.safety_flags(**kwargs)
    assert f.restricted and not f.allow_weight_loss and not f.allow_menus and f.reasons
    assert "dietista-nutricionista" in f.text


def test_safety_flags_cuando_adulto_sano_entonces_sin_restricciones():
    f = nu.safety_flags(30, conditions=["", "  "])
    assert not f.restricted and f.allow_menus and f.allow_weight_loss and f.reasons == []


# ─── Límites y referencias ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "call",
    [lambda: nu.bmr("hombre", 0, 180, 30), lambda: nu.bmr("x", 70, 180, 30),
     lambda: nu.bmr("hombre", 70, 180, 30, lean_mass_kg=80), lambda: nu.day_load_level(-1),
     lambda: nu.during_session(-10), lambda: nu.during_session(60, product_carbs_g=0),
     lambda: nu.during_session(60, "rarísima"), lambda: nu.hydration(70, 69, 0.5, 0),
     lambda: nu.hydration(0, 69, 0.5, 1), lambda: nu.hydration(70, 69, -1, 1),
     lambda: nu.race_plan(10_000, 2700, 0), lambda: nu.race_plan(10_000, -5, 60),
     lambda: nu.recovery(-1, 60), lambda: nu.energy_availability(2000, 500, 0),
     lambda: nu.safety_flags(0), lambda: nu.daily_targets("mujer", 0, 165, 30),
     lambda: nu.daily_targets("mujer", 60, 165, 30, planned_minutes=-30),
     lambda: nu.daily_targets("mujer", 60, 165, 30, activity_factor=3)],
)  # fmt: skip
def test_limites_cuando_valores_invalidos_entonces_value_error(call):
    with pytest.raises(ValueError):
        call()


def test_referencias_cuando_se_consultan_entonces_tienen_autor_anio_y_titulo():
    assert {"acsm2016", "ioc2011", "jeukendrup2014", "issn2021", "ioc2018", "ioc2023"} <= set(nu.REFERENCES)
    assert all(r.author and r.year > 1900 and r.title for r in nu.REFERENCES.values())
    assert "no sustituye a un dietista-nutricionista" in nu.DISCLAIMER
