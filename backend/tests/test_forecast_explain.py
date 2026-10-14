from datetime import date

import pytest

from app.services import forecast_explain as fx
from app.services import race_forecast as rf

TODAY = date(2026, 10, 14)


def data(**overrides) -> rf.TrainingData:
    base = {
        "efforts": {"best_5k": (5000.0, 1500.0, TODAY), "best_10k": (10000.0, 3150.0, TODAY)},
        "vo2max": 44.0,
        "km_per_week": 45.0,
        "avg_pace_s_km": 330.0,
        "longest_run_m": 25000.0,
    }
    return rf.TrainingData(**(base | overrides))


def points(result: dict) -> dict[str, str]:
    return {p["title"]: p["text"] for p in result["points"]}


def explain(distance=10000.0, target=None, evolution=None, then=None, **data_overrides) -> dict:
    d = data(**data_overrides)
    f = rf.forecast(distance, d)
    needed = rf.vdot(distance, target) if target else None
    return fx.explain_forecast(f, d, distance, target, needed, 8, evolution or [], then)


def test_loss_per_doubling_cuando_exponente_estandar_entonces_4_2_por_ciento():
    assert fx.loss_per_doubling(1.06) == pytest.approx(4.25, abs=0.01)
    assert fx.loss_per_doubling(1.0) == 0


def test_explicacion_cuando_marca_de_referencia_entonces_la_cita_con_fecha_y_vdot():
    text = points(explain())["Tu punto de partida"]
    # La de 5 km (25:00, VDOT 38,3) indica mejor forma que la de 10 km (52:30): es la elegida.
    assert "5 km" in text and "25:00" in text and "14/10/2026" in text and "VDOT 38,3" in text.replace("de ", "")
    assert "entrenamientos" in text


def test_explicacion_cuando_exponente_personal_alto_entonces_perfil_de_velocidad():
    efforts = {
        "best_1k": (1000.0, 240.0, TODAY),
        "best_5k": (5000.0, 1400.0, TODAY),
        "best_10k": (10000.0, 3100.0, TODAY),
    }
    text = points(explain(efforts=efforts))["Cómo pierdes ritmo con la distancia"]
    assert "más rápido en corto" in text and "1 km, 5 km, 10 km" in text


def test_explicacion_cuando_sin_distancias_variadas_entonces_exponente_general():
    text = points(explain(efforts={"best_5k": (5000.0, 1500.0, TODAY)}))["Cómo pierdes ritmo con la distancia"]
    assert "exponente general" in text


def test_explicacion_cuando_maraton_con_poco_volumen_entonces_explica_por_que_no_usa_tanda():
    text = points(explain(42195, km_per_week=15))["Qué dice cada modelo"]
    assert "Tanda no se usa" in text and "15 km/semana" in text


def test_explicacion_cuando_maraton_con_volumen_entonces_justifica_peso_de_tanda():
    text = points(explain(42195, km_per_week=60, longest_run_m=32000))["Qué dice cada modelo"]
    assert "Tanda pesa más" in text


def test_explicacion_cuando_no_has_corrido_la_distancia_entonces_lo_da_como_motivo_del_rango():
    text = points(explain(21097.5, longest_run_m=12000))["Por qué este rango"]
    assert "aún no has corrido la distancia" in text


def test_explicacion_cuando_objetivo_alcanzable_y_ambicioso():
    alcanzable = points(explain(target=3000))["Qué te falta"]
    ambicioso = points(explain(target=2700))["Qué te falta"]
    ya = points(explain(target=4000))["Qué te falta"]
    assert "alcanzable" in alcanzable
    assert "ambicioso" in ambicioso
    assert ya.startswith("Nada")


def test_explicacion_cuando_volumen_y_tirada_bajos_entonces_propone_palancas():
    text = points(explain(21097.5, target=5400, km_per_week=15, longest_run_m=12000))["Qué te falta"]
    assert "km/semana" in text and "tirada larga" in text


def test_explicacion_cuando_evolucion_mejora_entonces_cuenta_cuanto_y_por_que():
    evolution = [
        {"day": date(2026, 8, 23), "probable_s": 3300},
        {"day": date(2026, 10, 11), "probable_s": 3150},
    ]
    then = data(km_per_week=30, longest_run_m=15000, efforts={"best_5k": (5000.0, 1560.0, date(2026, 8, 1))})
    text = points(explain(evolution=evolution, then=then))["Cómo ha evolucionado"]
    assert "ha mejorado 2:30" in text
    assert "marca de referencia ha pasado de tu 5 km de 26:00" in text and "a tu 5 km de 25:00" in text
    assert "A tu favor" in text and "de 30 a 45 km/semana" in text and "de 15 a 25 km" in text


def test_explicacion_cuando_empeora_por_marca_antigua_entonces_no_culpa_al_volumen():
    # Regresión con datos reales: más volumen y tirada más larga aparecían como causa de empeorar.
    evolution = [{"day": date(2026, 7, 1), "probable_s": 3000}, {"day": date(2026, 10, 11), "probable_s": 3300}]
    then = data(km_per_week=5, longest_run_m=4500, efforts={"best_5k": (5000.0, 1400.0, date(2026, 6, 1))})
    now_efforts = {"best_5k": (5000.0, 1560.0, TODAY), "best_10k": (10000.0, 3300.0, TODAY)}
    text = points(explain(evolution=evolution, then=then, efforts=now_efforts, km_per_week=15,
                          longest_run_m=11200))["Cómo ha evolucionado"]  # fmt: skip
    assert "ha empeorado" in text and "fuera de la ventana de 6 meses" in text
    assert "A tu favor: has subido el volumen" in text
    assert "porque has subido" not in text


def test_explicacion_cuando_sin_calibrar_entonces_invita_a_marcar_carreras():
    assert "Aún no hay carreras marcadas" in points(explain())["Calibración con tus carreras"]


def test_explicacion_cuando_sin_datos_entonces_mensaje_simple():
    d = data(efforts={}, vo2max=None)
    result = fx.explain_forecast(rf.forecast(10000, d), d, 10000, None, None, 8, [], None)
    assert result["points"] == [] and "no hay datos" in result["summary"].lower()


def test_explain_paces_cuando_marca_entonces_origen_y_cinco_zonas():
    result = fx.explain_paces(rf.forecast(10000, data()))
    assert "VDOT 38,3" in result["summary"] and "5 km" in result["summary"]
    assert [z["key"] for z in result["zones"]] == ["easy", "marathon", "threshold", "interval", "repetition"]
    assert result["zones"][0]["percent"] == "59–74 % del VDOT"
    assert {s["label"].split(" ·")[0] for s in result["sources"]} >= {"Daniels"}
