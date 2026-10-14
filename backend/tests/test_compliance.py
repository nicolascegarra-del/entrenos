from datetime import UTC, date, datetime

import pytest

from app.models import BlockKind, PlannedBlock
from app.services.compliance import Segment, align_laps, compute_compliance, score_step, split_streams
from app.services.plan_steps import Step, estimated_duration_s, expand_steps, local_day, sport_family


def block(position: int, kind: BlockKind, **kw) -> PlannedBlock:
    return PlannedBlock(session_id=1, position=position, kind=kind, **kw)


def lap(index: int, distance_m: float, duration_s: float, hr: float = 140, **metrics) -> dict:
    return {
        "index": index,
        "distance_m": distance_m,
        "duration_s": duration_s,
        "avg_hr": hr,
        "avg_speed": distance_m / duration_s,
        "metrics": metrics,
    }


SERIES_PLAN = [
    block(0, BlockKind.WARMUP, distance_m=2000),
    block(
        1,
        BlockKind.INTERVAL,
        repeat=6,
        distance_m=200,
        target_metric="pace",
        target_min=190,  # 3:10 /km
        target_max=220,  # 3:40 /km
        recovery_duration_s=90,
    ),
    block(
        2,
        BlockKind.INTERVAL,
        repeat=4,
        distance_m=450,
        target_metric="pace",
        target_min=310,
        target_max=330,
        recovery_duration_s=75,
    ),  # fmt: skip
    block(3, BlockKind.COOLDOWN, distance_m=900),
]


def series_laps() -> list[dict]:
    """Vueltas reales de una sesión de series, con un lap accidental de 8 m tras calentar."""
    laps = [lap(0, 2130, 876, 120), lap(1, 8, 35, 89)]
    reps = [(195, 45), (189, 36), (209, 47), (202, 37), (196, 47), (192, 38)]  # ritmos 3:02–4:01
    for i, (d, t) in enumerate(reps):
        laps.append(lap(len(laps), d, t, 135))
        if i < 5:
            laps.append(lap(len(laps), 30, 90, 125))
    for i in range(4):
        laps.append(lap(len(laps), 452, 146, 148))  # ~5:23 /km
        if i < 3:
            laps.append(lap(len(laps), 22, 75, 140))
    laps.append(lap(len(laps), 899, 332, 150))
    return laps


def test_expand_steps_cuando_series_con_recuperacion_entonces_intercaladas_sin_la_ultima():
    steps = expand_steps(SERIES_PLAN)
    kinds = [s.kind for s in steps]
    assert len(steps) == 1 + (6 + 5) + (4 + 3) + 1
    assert kinds[1:4] == ["interval", "recovery", "interval"]
    assert steps[11].kind == "interval" and steps[12].kind == "interval"  # última serie sin recuperación
    assert steps[1].label == "Serie 1" and steps[2].label == "Recuperación 1"
    assert steps[0].label == "Calentamiento"


def test_estimated_duration_cuando_distancia_con_ritmo_entonces_usa_ritmo_medio():
    steps = [Step(0, "interval", 0, None, 1000, "pace", 240, 260)]
    assert estimated_duration_s(steps) == 250


@pytest.mark.parametrize(
    ("sport", "family"),
    [("treadmill_running", "running"), ("road_biking", "cycling"), ("yoga", "yoga")],
)
def test_sport_family_cuando_variantes_entonces_agrupa(sport, family):
    assert sport_family(sport) == family


def test_local_day_cuando_actividad_nocturna_utc_entonces_dia_local():
    start = datetime(2026, 10, 14, 23, 30, tzinfo=UTC)
    assert local_day(start, "+02:00") == date(2026, 10, 15)
    assert local_day(start, "-05:00") == date(2026, 10, 14)
    assert local_day(start, None) == date(2026, 10, 14)


def test_align_laps_cuando_lap_accidental_entonces_lo_ignora_y_alinea_series():
    steps = expand_steps(SERIES_PLAN)
    segments, unplanned = align_laps(steps, series_laps())
    # El lap de 8 m se absorbe en el calentamiento o queda fuera: nunca descuadra las series.
    assert segments[0].laps in ([0], [0, 1])
    assert unplanned in ([], [1])
    assert [segments[i].laps for i in (1, 3, 5)] == [[2], [4], [6]]  # series de 200 m
    assert segments[12].laps == [13]  # primera de 450 m
    assert segments[-1].laps == [20]  # vuelta a la calma


def test_compute_compliance_cuando_series_reales_entonces_nota_y_estados_por_paso():
    detail = compute_compliance(expand_steps(SERIES_PLAN), series_laps(), {})
    assert detail["method"] == "laps"
    steps = detail["steps"]
    # 189 m en 36 s = 3:10 /km → dentro del rango
    assert steps[3]["status"] == "ok" and steps[3]["direction"] is None
    # 209 m en 47 s = 3:45 /km → algo lento
    assert steps[5]["direction"] == "slow" and steps[5]["status"] in ("ok", "near")
    # 450 m a ~5:23 /km frente a 5:10–5:30 → en rango
    assert steps[12]["status"] == "ok"
    # Recuperaciones y calentamiento no tienen nota, solo estado por volumen
    assert steps[0]["score"] is None and steps[0]["status"] == "ok"
    assert 0 < detail["score"] <= 100


def test_score_step_cuando_ritmo_6pct_lento_entonces_70_y_ambar():
    step = Step(0, "interval", 1, None, 1000, "pace", 240, 260)
    seg = Segment(duration_s=1000 / (1000 / 275), distance_m=1000)  # 4:35 /km, 15 s sobre 4:20
    result = score_step(step, seg)
    assert result["direction"] == "slow"
    assert result["score"] == pytest.approx(70, abs=0.2)  # 15 s / 250 s de media = 6 % → 100 − 30
    assert result["status"] == "near"


def test_score_step_cuando_ritmo_muy_lento_entonces_rojo():
    step = Step(0, "interval", 1, None, 1000, "pace", 240, 260)
    result = score_step(step, Segment(duration_s=300, distance_m=1000))  # 5:00 /km
    assert result["score"] == 20 and result["status"] == "off"  # 16 % fuera


def test_score_step_cuando_fc_por_encima_entonces_alto():
    step = Step(0, "steady", 0, 1800, None, "hr", None, 150)
    result = score_step(step, Segment(duration_s=1800, distance_m=5000, hr=153))
    assert result["direction"] == "high"
    assert result["status"] == "ok"  # 2 % por encima → 90


def test_score_step_cuando_no_completa_entonces_penaliza():
    step = Step(0, "interval", 1, None, 1000, "pace", 240, 260)
    result = score_step(step, Segment(duration_s=125, distance_m=500))  # buen ritmo pero solo 500 m
    assert result["completion"] == 0.5
    assert result["score"] == 50


def test_score_step_cuando_sin_dato_de_potencia_entonces_cero():
    step = Step(0, "interval", 1, 300, None, "power", 250, 270)
    result = score_step(step, Segment(duration_s=300, distance_m=2000))
    assert result["score"] == 0 and result["status"] == "off"


def test_compute_compliance_cuando_una_sola_vuelta_entonces_divide_el_stream():
    steps = expand_steps(
        [
            block(0, BlockKind.WARMUP, duration_s=10),
            block(1, BlockKind.STEADY, duration_s=10, target_metric="hr", target_min=150, target_max=160),
        ]
    )
    channels = {
        "time": [float(t) for t in range(21)],
        "distance": [t * 3.0 for t in range(21)],
        "hr": [120.0] * 11 + [155.0] * 10,
    }
    detail = compute_compliance(steps, [lap(0, 60, 20)], channels)
    assert detail["method"] == "streams"
    assert detail["steps"][1]["actual"]["value"] == pytest.approx(155, abs=4)
    assert detail["steps"][1]["status"] == "ok"


def test_split_streams_cuando_paso_libre_final_entonces_resto_de_actividad():
    steps = [Step(0, "warmup", 0, 5, None), Step(1, "steady", 0, None, None)]
    segments = split_streams(steps, {"time": [float(t) for t in range(11)], "distance": [t * 2.0 for t in range(11)]})
    assert segments[0].duration_s == 5 and segments[1].duration_s == 5


def test_compute_compliance_cuando_sin_objetivos_entonces_volumen_completado():
    steps = expand_steps([block(0, BlockKind.STEADY, distance_m=5000)])
    detail = compute_compliance(steps, [lap(0, 4500, 1500), lap(1, 10, 5)], {})
    assert detail["score"] == pytest.approx(90, abs=1)


def test_compute_compliance_cuando_sin_pasos_entonces_vacio():
    assert compute_compliance([], [], {})["score"] is None


def test_align_laps_cuando_descanso_largo_entre_bloques_entonces_queda_fuera_del_plan():
    # Regresión con datos reales: tras la última serie de 200 m hubo 222 s andando (78 m)
    # antes del bloque de 450 m; no debe fusionarse con la primera serie de 450 m.
    plan = [
        block(
            0,
            BlockKind.INTERVAL,
            repeat=2,
            distance_m=200,
            target_metric="pace",
            target_min=190,
            target_max=220,
            recovery_duration_s=90,
        ),  # fmt: skip
        block(
            1,
            BlockKind.INTERVAL,
            repeat=2,
            distance_m=450,
            target_metric="pace",
            target_min=310,
            target_max=330,
            recovery_duration_s=75,
        ),  # fmt: skip
    ]
    laps = [lap(0, 196, 47), lap(1, 30, 90), lap(2, 192, 38), lap(3, 78, 222), lap(4, 452, 146), lap(5, 22, 75),
            lap(6, 454, 148)]  # fmt: skip
    segments, unplanned = align_laps(expand_steps(plan), laps)
    assert unplanned == [3]
    assert segments[3].laps == [4]
    detail = compute_compliance(expand_steps(plan), laps, {})
    assert detail["steps"][3]["status"] == "ok"
