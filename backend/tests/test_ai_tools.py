import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlmodel import Session

from app.core.security import create_token
from app.models import (
    Activity,
    ActivityFeedback,
    ActivityStream,
    AiProvider,
    ChatMessage,
    DailyMetric,
    Lap,
    PlannedSession,
    User,
)
from app.services import ai_tools
from app.services.llm import ToolCall, stream_chat

TODAY = date.today()


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _run(session: Session, user: User, days_ago: int = 2, km: float = 6.0, name: str = "Series") -> Activity:
    start = datetime.now(UTC) - timedelta(days=days_ago)
    seconds = int(km * 300)
    a = Activity(
        user_id=user.id,
        sport="running",
        name=name,
        start_time=start,
        duration_s=seconds,
        moving_duration_s=seconds,
        distance_m=km * 1000,
        avg_hr=152,
        max_hr=171,
        elevation_gain_m=40,
        metrics={"aerobic_te": 3.4, "avg_cadence": 168, "best_1k": 270, "hr_zone_4_s": 600},
    )
    session.add(a)
    session.flush()
    n = seconds // 5
    channels = {
        "time": [i * 5.0 for i in range(n)],
        "distance": [i * 5 * 1000 / 300 for i in range(n)],
        "hr": [130 + (i % 40) for i in range(n)],
        "speed": [3.33] * n,
        "altitude": [10.0] * n,
        "lat": [37.6] * n,
        "lon": [-0.98] * n,
    }
    for ch, values in channels.items():
        session.add(ActivityStream(activity_id=a.id, channel=ch, values=values))
    session.add(
        Lap(
            activity_id=a.id,
            index=0,
            start_offset_s=0,
            duration_s=600,
            distance_m=2000,
            avg_hr=145,
            max_hr=160,
            avg_speed=3.33,
            metrics={"avg_cadence": 166},
        )
    )
    session.add(ActivityFeedback(activity_id=a.id, rpe=7, feeling=4, notes="Piernas bien"))
    session.commit()
    session.refresh(a)
    return a


def _call(session, user, name, **args):
    label, text = ai_tools.execute(session, user.id, name, args)
    return label, json.loads(text.split(" [resultado recortado")[0]) if text.startswith("{") else text


# ─── Herramientas ────────────────────────────────────────────────────────────


def test_buscar_actividades_por_fechas_y_deporte(session, user):
    _run(session, user, 2, name="Series")
    _run(session, user, 40, name="Rodaje viejo")
    label, data = _call(session, user, "buscar_actividades")
    assert data["total_en_el_periodo"] == 1 and data["actividades"][0]["nombre"] == "Series"
    assert data["actividades"][0]["ritmo"] == "5:00/km" and "Actividades del" in label
    _, data = _call(session, user, "buscar_actividades", desde=(TODAY - timedelta(days=60)).isoformat(), texto="viejo")
    assert [a["nombre"] for a in data["actividades"]] == ["Rodaje viejo"]
    _, data = _call(session, user, "buscar_actividades", deporte="cycling")
    assert data["actividades"] == []


def test_detalle_completo_sin_gps(session, user):
    a = _run(session, user)
    session.add(
        PlannedSession(
            user_id=user.id,
            day=TODAY,
            sport="running",
            title="6x1000",
            activity_id=a.id,
            compliance_score=88,
            compliance_detail={"steps": [{"status": "ok", "score": 92}]},
        )
    )
    session.commit()
    label, data = _call(session, user, "detalle_actividad", id=a.id)
    assert label.startswith("Detalle de «Series»")
    assert data["vueltas"][0] == {
        "n": 1,
        "km": 2.0,
        "tiempo": "10:00",
        "ritmo": "5:00/km",
        "fc_media": 145,
        "fc_max": 160,
        "cadencia": 166,
    }
    assert data["parciales_km"][0]["tiempo"] == "5:00" and len(data["parciales_km"]) == 5
    assert data["sensaciones"] == {"rpe_1a10": 7, "como_te_sentiste_1a5": 4, "notas": "Piernas bien"}
    assert data["sesion_planificada"]["cumplimiento_pct"] == 88
    assert data["metricas_del_reloj"]["Mejor 1 km"] == "4:30"
    assert "desacople_fc_ritmo_pct" in data
    text = json.dumps(data)
    assert "37.6" not in text and "-0.98" not in text  # nunca coordenadas


def test_series_reducidas_y_como_ritmo(session, user):
    a = _run(session, user)
    _, data = _call(session, user, "series_actividad", id=a.id, canales=["fc", "velocidad"])
    assert len(data["puntos"]) <= ai_tools.MAX_SERIES_POINTS and data["puntos"][0]["velocidad"] == "5:00/km"
    _, data = _call(session, user, "series_actividad", id=a.id, canales=["lat"])
    assert "error" in data


def test_actividad_ajena_o_inexistente(session, user):
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    a = _run(session, other)
    _, data = _call(session, user, "detalle_actividad", id=a.id)
    assert "No existe" in data["error"]
    _, data = _call(session, user, "detalle_actividad", id="abc")
    assert "número" in data["error"]
    _, data = _call(session, user, "buscar_actividades", desde="ayer")
    assert "Fecha no válida" in data["error"]
    label, data = _call(session, user, "no_existe")
    assert "desconocida" in label


def test_progresion_salud_marcas_y_plan(session, user):
    for d in range(1, 30, 3):
        _run(session, user, d, name=f"R{d}")
    session.add(
        DailyMetric(
            user_id=user.id,
            day=TODAY - timedelta(days=1),
            metrics={"resting_hr": 48, "sleep_seconds": 27000, "hrv_last_night": 61},
        )
    )
    session.commit()
    _, forma = _call(session, user, "progresion", metrica="forma", dias=30)
    assert {"forma_ctl", "fatiga_atl", "frescura_tsb"} <= forma["datos"][-1].keys()
    _, vol = _call(session, user, "progresion", metrica="volumen", dias=21)
    assert sum(w["sesiones"] for w in vol["datos"]) >= 7
    _, ef = _call(session, user, "progresion", metrica="eficiencia")
    assert ef["datos"] and "m_min_por_ppm" in ef["datos"][0]
    _, bad = _call(session, user, "progresion", metrica="bitcoin")
    assert "Métrica no válida" in bad["error"]
    _, salud = _call(session, user, "salud_diaria")
    assert salud["dias"][0] == {"dia": str(TODAY - timedelta(days=1)), "fc_reposo": 48, "hrv_ms": 61, "sueno_h": 7.5}
    _, marcas = _call(session, user, "marcas_y_previsiones")
    assert marcas["marcas"][0]["mejor"] == "4:30"
    _, plan = _call(session, user, "plan_y_objetivos")
    assert "sesiones" in plan or plan == {}
    _, zonas = _call(session, user, "zonas_y_umbrales")
    assert "zonas_fc" in zonas
    _, les = _call(session, user, "lesiones_y_material")
    assert les["estado"] in ("good", "watch", "alert")


def test_resultado_recortado(session, user, monkeypatch):
    monkeypatch.setattr(ai_tools, "MAX_RESULT_CHARS", 200)
    for d in range(1, 10):
        _run(session, user, d)
    _, text = ai_tools.execute(session, user.id, "buscar_actividades", {})
    assert text.endswith("[resultado recortado: pide un rango más corto]")


# ─── Bucle de herramientas con cada proveedor ────────────────────────────────


def _sse(*events: dict) -> bytes:
    return "".join(f"data: {json.dumps(e)}\n\n" for e in events).encode()


ROUND1 = {
    AiProvider.ANTHROPIC: _sse(
        {"type": "message_start", "message": {"usage": {"input_tokens": 100}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Miro tus datos."}},
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "tool_use", "id": "tu_1", "name": "detalle_actividad", "input": {}},
        },
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"id":'}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": " 7}"}},
        {"type": "message_delta", "usage": {"output_tokens": 20}},
    ),
    AiProvider.OPENAI: _sse(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {"name": "detalle_actividad", "arguments": '{"id"'},
                            }
                        ]
                    }
                }
            ]
        },
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": ": 7}"}}]}}]},
        {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 20}},
    ),
    AiProvider.GEMINI: _sse(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {"name": "detalle_actividad", "args": {"id": 7}},
                                "thoughtSignature": "firma",
                            }
                        ]
                    }
                }
            ],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20},
        },
    ),
}
ROUND2 = {
    AiProvider.ANTHROPIC: _sse(
        {"type": "message_start", "message": {"usage": {"input_tokens": 300}}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Ritmo 5:00."}},
        {"type": "message_delta", "usage": {"output_tokens": 30}},
    ),
    AiProvider.OPENAI: _sse(
        {"choices": [{"delta": {"content": "Ritmo 5:00."}}]},
        {"choices": [], "usage": {"prompt_tokens": 300, "completion_tokens": 30}},
    ),
    AiProvider.GEMINI: _sse(
        {
            "candidates": [{"content": {"parts": [{"text": "Ritmo 5:00."}]}}],
            "usageMetadata": {"promptTokenCount": 300, "candidatesTokenCount": 30},
        }
    ),
}


@pytest.mark.parametrize("provider", list(ROUND1))
def test_bucle_de_herramientas(provider):
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, content=(ROUND1 if len(bodies) == 1 else ROUND2)[provider])

    executed = []

    def executor(call: ToolCall) -> tuple[str, str]:
        executed.append((call.name, call.args))
        return "Detalle de «Series»", '{"ritmo":"5:00/km"}'

    tools = ai_tools.TOOLS[:2]
    chunks = list(
        stream_chat(
            provider,
            "sk-1234567890",
            "m",
            "sys",
            [{"role": "user", "content": "¿Qué tal?"}],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            tools=tools,
            executor=executor,
        )
    )
    assert executed == [("detalle_actividad", {"id": 7})]
    assert [c.tool for c in chunks if c.tool] == ["Detalle de «Series»"]
    assert "Ritmo 5:00." in "".join(c.text for c in chunks)
    assert (chunks[-1].input_tokens, chunks[-1].output_tokens) == (400, 50)  # suma de las dos rondas
    second = json.dumps(bodies[1])
    assert '"ritmo\\":\\"5:00/km' in second or "5:00/km" in second  # el resultado vuelve al modelo
    if provider == AiProvider.GEMINI:
        assert "firma" in second and bodies[0]["tools"][0]["functionDeclarations"][0]["parameters"]["type"] == "OBJECT"
    if provider == AiProvider.ANTHROPIC:
        assert bodies[1]["messages"][-1]["content"][0]["type"] == "tool_result"
    if provider == AiProvider.OPENAI:
        assert bodies[1]["messages"][-1] == {"role": "tool", "tool_call_id": "call_1", "content": '{"ritmo":"5:00/km"}'}


def test_tope_de_rondas_obliga_a_responder(monkeypatch):
    import app.services.llm as llm

    monkeypatch.setattr(llm, "MAX_TOOL_ROUNDS", 2)
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, content=ROUND1[AiProvider.OPENAI])

    chunks = list(
        stream_chat(
            AiProvider.OPENAI,
            "sk-1234567890",
            "m",
            "s",
            [{"role": "user", "content": "x"}],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            tools=ai_tools.TOOLS,
            executor=lambda c: ("x", "{}"),
        )
    )
    # 2 rondas con herramientas, 1 obligada a responder y, como sigue sin escribir, el empujón final.
    assert len(bodies) == 4 and bodies[2]["tool_choice"] == "none" and bodies[3]["tool_choice"] == "none"
    assert "no has escrito ninguna respuesta" in bodies[3]["messages"][-1]["content"]
    assert len([c for c in chunks if c.tool]) == 2


# ─── API ─────────────────────────────────────────────────────────────────────


def test_api_chat_con_herramientas(client, user, session, monkeypatch):
    from app.api import ai as ai_api
    from app.models import AiProviderConfig
    from app.services.llm import Chunk

    a = _run(session, user)
    session.add(
        AiProviderConfig(
            user_id=user.id,
            provider=AiProvider.ANTHROPIC,
            model="claude-haiku-5-5",
            key_enc=ai_api.encrypt_secret("sk-ant-1234567890"),
            key_last4="7890",
            enabled=True,
            is_default=True,
        )
    )
    session.commit()
    seen = {}

    def fake(provider, api_key, model, system, messages, client=None, tools=None, executor=None):
        seen["system"], seen["tools"] = system, [t.name for t in tools]
        label, result = executor(ToolCall("t1", "detalle_actividad", {"id": a.id}))
        seen["result"] = json.loads(result)
        yield Chunk(tool=label)
        yield Chunk(text="**Qué he mirado** tu entreno.")
        yield Chunk(input_tokens=10, output_tokens=5)

    monkeypatch.setattr(ai_api, "stream_chat", fake)
    res = client.post("/api/v1/chat", json={"message": "Analiza mi último entreno"}, headers=auth(user))
    assert "event: tool" in res.text and "Detalle de «Series»" in res.text
    assert f"id {a.id}" in seen["system"] and "detalle_actividad" in seen["tools"]
    assert seen["result"]["vueltas"][0]["ritmo"] == "5:00/km"
    msg = session.exec(ChatMessage.__table__.select().where(ChatMessage.role == "assistant")).first()  # type: ignore[attr-defined]
    assert msg.tools == [f"Detalle de «Series» del {a.start_time.astimezone(UTC).strftime('%d/%m/%Y')}"] or msg.tools
    conv = client.get("/api/v1/chat/conversations", headers=auth(user)).json()[0]
    detail = client.get(f"/api/v1/chat/conversations/{conv['id']}", headers=auth(user)).json()
    assert detail["messages"][-1]["tools"]
