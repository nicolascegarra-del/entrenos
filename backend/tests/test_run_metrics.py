"""Indicadores de carrera: GAP, eficiencia, condición de rendimiento y carga de la sesión."""

from datetime import UTC, datetime, timedelta

from app.models import Activity
from app.services import run_metrics


def test_gap_factor_cuando_llano_entonces_1_y_cuando_sube_mayor():
    dist = [i * 50.0 for i in range(21)]
    assert run_metrics.gap_factor(dist, [100.0] * 21) == 1.0
    assert run_metrics.gap_factor(dist, [100 + i * 3.0 for i in range(21)]) > 1.1  # 6 % de subida
    assert run_metrics.gap_factor(dist, [100 - i * 1.0 for i in range(21)]) < 1.0  # bajada suave ayuda


def test_gap_factor_cuando_no_hay_altitud_entonces_none():
    assert run_metrics.gap_factor([0, 100], [None, None]) is None
    assert run_metrics.gap_pace(300, None) is None


def test_gap_pace_cuando_cuesta_un_10_mas_entonces_ritmo_en_llano_mas_rapido():
    assert run_metrics.gap_pace(330, 1.1) == 300


def test_eficiencia_cuando_datos_validos_entonces_metros_minuto_por_pulsacion():
    assert run_metrics.efficiency_index(1000, 300, 150) == round(200 / 150, 3)
    assert run_metrics.efficiency_index(1000, 300, None) is None


def test_condicion_cuando_el_reloj_la_da_entonces_inicial_final_y_curva():
    time = list(range(0, 1800, 60))
    watch = [None] * 6 + [3, 4, 4, 3] + [2] * 10 + [0, -1] * 5
    out = run_metrics.performance_condition(time, watch, None, None)
    assert out["source"] == "reloj" and out["final"] == -1 and out["min"] == -1
    assert out["initial"] in (2, 3, 4) and out["series"]


def test_condicion_cuando_no_hay_reloj_entonces_estimada_y_acotada():
    out = run_metrics.performance_condition([0, 60], None, 1.05, 1.0)
    assert out == {"source": "estimado", "initial": 5, "final": None, "min": None, "series": []}
    assert run_metrics.performance_condition([0], None, 2.0, 1.0)["initial"] == 20  # tope +20
    assert run_metrics.performance_condition([0], None, None, 1.0) is None


def test_recuperacion_cuando_sube_la_carga_entonces_mas_horas():
    assert run_metrics.recovery_hours(30) == (12, 24)
    assert run_metrics.recovery_hours(120) == (24, 48)
    assert run_metrics.recovery_hours(400) == (72, 96)


def _run(user_id: int, start: datetime, km: float = 10, minutes: float = 50, hr: float = 150) -> Activity:
    return Activity(user_id=user_id, sport="running", start_time=start, duration_s=minutes * 60,
                    moving_duration_s=minutes * 60, distance_m=km * 1000, avg_hr=hr)  # fmt: skip


def test_referencia_cuando_hay_carreras_anteriores_entonces_media_y_delta(session, user):
    now = datetime(2026, 10, 20, 8, tzinfo=UTC)
    for i in range(3):
        session.add(_run(user.id, now - timedelta(days=5 + i), hr=160))
    today = _run(user.id, now, hr=150)
    session.add(today)
    session.commit()
    out = run_metrics.summary(session, today, {}, [], 60.0)
    eff = out["efficiency"]
    assert eff["baseline_runs"] == 3 and eff["delta_pct"] > 0  # misma velocidad con menos FC
    assert out["load"]["load"] == 60.0 and out["load"]["recovery_h"] == [24, 48]


def test_referencia_cuando_pocas_carreras_entonces_sin_comparacion(session, user):
    today = _run(user.id, datetime(2026, 10, 20, 8, tzinfo=UTC))
    session.add(today)
    session.commit()
    eff = run_metrics.summary(session, today, {}, [], 40.0)["efficiency"]
    assert eff["baseline"] is None and eff["delta_pct"] is None and eff["value"] > 0


def test_resumen_cuando_no_es_carrera_entonces_solo_carga():
    act = Activity(user_id=1, sport="cycling", start_time=datetime(2026, 10, 20, tzinfo=UTC), duration_s=3600)
    out = run_metrics.empty(act, 80.0)
    assert out["efficiency"] is None and out["gap"] is None and out["load"]["intensity"] == round((0.8) ** 0.5, 2)
