import json
from datetime import date

from app.models import RestPeriod
from app.services import ai_tools, oura_sync
from app.services.ai_context import format_context
from app.services.injury import injury_report
from tests.oura_fake import DAY, connect
from tests.test_oura_sync import _load_all


def _call(session, user, name: str, **args) -> dict:
    _, text = ai_tools.execute(session, user.id, name, args)
    return json.loads(text)


def test_noche_detalle_cuando_hay_oura_entonces_resumen_de_fases_curvas_y_siestas(session, user, oura):
    connect(session, user)
    _load_all(oura)
    oura_sync.sync_range(session, user.id, DAY, DAY)
    data = _call(session, user, "noche_detalle", dia=DAY.isoformat())
    assert data["fuente"] == "oura" and data["principal"]["sueno_min"] == 450
    assert data["fases"] == {"profundo_min": 15, "ligero_min": 15, "rem_min": 10, "despierto_min": 10,
                             "despertares": 1, "primer_profundo_min": 15}  # fmt: skip
    assert data["fc_noche"] == {"min": 47, "max": 55, "media": 50, "por_tercios": [55, 50, 48]}
    assert [s["sueno_min"] for s in data["siestas"]] == [30]
    assert data["nota_sueno"] == 82 and data["preparacion"] == 76 and "Alcohol" in data["etiquetas"]


def test_noche_detalle_cuando_sin_datos_entonces_lo_dice(session, user):
    assert "No hay datos" in _call(session, user, "noche_detalle", dia="2026-01-01")["error"]


def test_salud_diaria_cuando_hay_oura_entonces_metricas_nuevas_etiquetas_y_modo_descanso(session, user, oura):
    connect(session, user)
    _load_all(oura)
    oura_sync.sync_range(session, user.id, DAY, DAY)
    data = _call(session, user, "salud_diaria", desde="2026-10-10", hasta="2026-10-25")
    day = data["dias"][0]
    assert day["preparacion"] == 76 and day["profundo_min"] == 90 and day["siestas_min"] == 30
    assert day["temp_desviacion_c"] == -0.21 and day["resiliencia_1a5"] == 3 and day["spo2"] == 97
    assert {t["etiqueta"] for t in data["etiquetas"]} == {"Alcohol", "Cena tarde"}
    assert data["modo_descanso"] == [{"desde": "2026-10-18", "hasta": "activo"}]


def test_lesiones_cuando_modo_descanso_activo_entonces_lo_menciona(session, user):
    session.add(RestPeriod(user_id=user.id, source="oura", external_id="r", start_date=date.today()))
    session.commit()
    report = injury_report(session, user.id)
    assert report["checks"][0]["key"] == "rest_mode" and report["rest_mode"]["end_date"] is None
    assert report["status"] in ("watch", "alert")


def test_contexto_ia_cuando_modo_descanso_entonces_seccion_propia():
    text = format_context({"rest_mode": {"start_date": "2026-10-18", "end_date": None}}, date(2026, 10, 20))
    assert "Modo descanso ACTIVO" in text and "sin fecha de fin" in text
