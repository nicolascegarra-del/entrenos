import json
from datetime import date

import pytest
from sqlmodel import Session, select

from app.api import ai as ai_api
from app.core.config import get_settings
from app.core.crypto import decrypt_secret
from app.core.security import create_token
from app.models import AiProviderConfig, ChatMessage, User
from app.services.ai_context import conversation_title, format_context
from app.services.llm import Chunk, LLMError

KEY = "sk-clave-de-prueba-9876"


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _save(client, user, provider="openai", **body) -> dict:
    payload = {"api_key": KEY, "model": "gpt-5-mini"} | body
    res = client.put(f"/api/v1/ai/providers/{provider}", json=payload, headers=auth(user))
    assert res.status_code == 200, res.text
    return {p["provider"]: p for p in res.json()["providers"]}


def _events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


@pytest.fixture(autouse=True)
def _model_ok(monkeypatch):
    """Por defecto el modelo responde al guardar (sin llamar a ningún proveedor)."""
    checked = []
    monkeypatch.setattr(ai_api, "check_model", lambda provider, key, model: checked.append((provider, key, model)))
    return checked


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    def fake(provider, api_key, model, system, messages, client=None):
        calls.append({"provider": provider, "api_key": api_key, "model": model, "system": system, "messages": messages})
        yield Chunk(text="Tu frescura ")
        yield Chunk(text="está bien.")
        yield Chunk(input_tokens=120, output_tokens=8)

    monkeypatch.setattr(ai_api, "stream_chat", fake)
    return calls


# ─── Cuentas ─────────────────────────────────────────────────────────────────


def test_guardar_proveedor_cuando_clave_entonces_cifrada_y_nunca_devuelta(client, user, session: Session):
    res = client.put("/api/v1/ai/providers/openai", json={"api_key": KEY, "model": "gpt-5-mini"}, headers=auth(user))
    assert KEY not in res.text
    openai = {p["provider"]: p for p in res.json()["providers"]}["openai"]
    assert openai["configured"] and openai["key_last4"] == "9876" and openai["is_default"]
    stored = session.exec(select(AiProviderConfig)).one()
    assert stored.key_enc != KEY and decrypt_secret(stored.key_enc) == KEY


def test_guardar_proveedor_cuando_nuevo_sin_clave_entonces_422(client, user):
    res = client.put("/api/v1/ai/providers/gemini", json={"model": "gemini-2.5-flash"}, headers=auth(user))
    assert res.status_code == 422


def test_guardar_proveedor_cuando_sin_clave_entonces_conserva_la_actual(client, user, session: Session):
    _save(client, user)
    _save(client, user, api_key=None, model="gpt-5")
    stored = session.exec(select(AiProviderConfig)).one()
    assert stored.model == "gpt-5" and decrypt_secret(stored.key_enc) == KEY


def test_predeterminado_cuando_se_marca_otro_entonces_solo_uno(client, user):
    _save(client, user)
    providers = _save(client, user, "anthropic", model="claude-haiku-5-5", is_default=True)
    assert providers["anthropic"]["is_default"] and not providers["openai"]["is_default"]


def test_borrar_predeterminado_entonces_pasa_a_otro_activo(client, user):
    _save(client, user)
    _save(client, user, "gemini", model="gemini-2.5-flash")
    assert client.delete("/api/v1/ai/providers/openai", headers=auth(user)).status_code == 204
    providers = {p["provider"]: p for p in client.get("/api/v1/ai/providers", headers=auth(user)).json()["providers"]}
    assert not providers["openai"]["configured"] and providers["gemini"]["is_default"]


def test_probar_clave_cuando_valida_entonces_modelos(client, user, monkeypatch):
    _save(client, user)
    monkeypatch.setattr(ai_api, "list_models", lambda provider, key: ["gpt-5-mini"] if key == KEY else [])
    checked = []
    monkeypatch.setattr(ai_api, "check_model", lambda provider, key, model: checked.append(model))
    res = client.post("/api/v1/ai/providers/openai/test", headers=auth(user))
    assert res.json() == {"ok": True, "model": "gpt-5-mini", "models": ["gpt-5-mini"]}
    assert checked == ["gpt-5-mini"]


def test_probar_clave_cuando_modelo_retirado_entonces_400_aunque_la_clave_valga(client, user, monkeypatch):
    _save(client, user)
    monkeypatch.setattr(ai_api, "list_models", lambda provider, key: ["gpt-5-mini"])

    def retired(provider, key, model):
        raise LLMError("El modelo no está disponible para tu clave; elige otro en Ajustes.", 404)

    monkeypatch.setattr(ai_api, "check_model", retired)
    res = client.post("/api/v1/ai/providers/openai/test", headers=auth(user))
    assert res.status_code == 400 and "elige otro" in res.json()["error"]["message"]


def test_probar_clave_cuando_invalida_entonces_400_con_motivo(client, user, monkeypatch):
    _save(client, user)

    def bad(provider, key):
        raise LLMError("La clave de API no es válida o no tiene permisos.", 401)

    monkeypatch.setattr(ai_api, "list_models", bad)
    res = client.post("/api/v1/ai/providers/openai/test", headers=auth(user))
    assert res.status_code == 400 and "no es válida" in res.json()["error"]["message"]


def test_proveedores_cuando_otro_usuario_entonces_no_ve_mis_claves(client, user, session: Session):
    _save(client, user)
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    providers = client.get("/api/v1/ai/providers", headers=auth(other)).json()["providers"]
    assert not any(p["configured"] for p in providers)


# ─── Chat ────────────────────────────────────────────────────────────────────


def test_chat_cuando_sin_asistente_entonces_409(client, user):
    res = client.post("/api/v1/chat", json={"message": "hola"}, headers=auth(user))
    assert res.status_code == 409 and "Ajustes" in res.json()["error"]["message"]


def test_chat_cuando_configurado_entonces_stream_y_guarda_conversacion(client, user, fake_llm, session: Session):
    _save(client, user)
    res = client.post("/api/v1/chat", json={"message": "¿Cómo está mi frescura?"}, headers=auth(user))
    assert res.headers["content-type"].startswith("text/event-stream")
    events = _events(res.text)
    assert [e for e, _ in events] == ["meta", "delta", "delta", "done"]
    conversation_id = events[0][1]["conversation_id"]
    assert fake_llm[0]["api_key"] == KEY and fake_llm[0]["model"] == "gpt-5-mini"
    assert "DATOS DEL USUARIO" in fake_llm[0]["system"] and user.email not in fake_llm[0]["system"]

    conversation = client.get(f"/api/v1/chat/conversations/{conversation_id}", headers=auth(user)).json()
    assert conversation["title"] == "¿Cómo está mi frescura?"
    assert [m["role"] for m in conversation["messages"]] == ["user", "assistant"]
    assert conversation["messages"][1]["content"] == "Tu frescura está bien."
    assistant = session.exec(select(ChatMessage).where(ChatMessage.role == "assistant")).one()
    assert (assistant.input_tokens, assistant.output_tokens) == (120, 8)


def test_chat_cuando_sigue_conversacion_entonces_envia_historial(client, user, fake_llm):
    _save(client, user)
    first = _events(client.post("/api/v1/chat", json={"message": "uno"}, headers=auth(user)).text)
    conversation_id = first[0][1]["conversation_id"]
    client.post("/api/v1/chat", json={"message": "dos", "conversation_id": conversation_id}, headers=auth(user))
    assert [m["content"] for m in fake_llm[1]["messages"]] == ["uno", "Tu frescura está bien.", "dos"]


def test_chat_cuando_error_del_proveedor_entonces_evento_error_sin_respuesta(client, user, monkeypatch, session):
    _save(client, user)

    def failing(*args, **kwargs):
        raise LLMError("Has superado el límite del proveedor o no te queda saldo en la cuenta.", 429)
        yield  # pragma: no cover

    monkeypatch.setattr(ai_api, "stream_chat", failing)
    events = _events(client.post("/api/v1/chat", json={"message": "hola"}, headers=auth(user)).text)
    assert events[-1][0] == "error" and "saldo" in events[-1][1]["message"]
    assert session.exec(select(ChatMessage).where(ChatMessage.role == "assistant")).first() is None


def test_chat_cuando_limite_diario_entonces_429(client, user, fake_llm, monkeypatch):
    _save(client, user)
    monkeypatch.setattr(get_settings(), "chat_daily_limit", 1)
    assert client.post("/api/v1/chat", json={"message": "uno"}, headers=auth(user)).status_code == 200
    res = client.post("/api/v1/chat", json={"message": "dos"}, headers=auth(user))
    assert res.status_code == 429 and "límite" in res.json()["error"]["message"]


def test_chat_cuando_conversacion_ajena_entonces_404(client, user, fake_llm, session: Session):
    _save(client, user)
    conversation_id = _events(client.post("/api/v1/chat", json={"message": "uno"}, headers=auth(user)).text)[0][1][
        "conversation_id"
    ]
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    _save(client, other)
    res = client.post("/api/v1/chat", json={"message": "x", "conversation_id": conversation_id}, headers=auth(other))
    assert res.status_code == 404
    assert client.get(f"/api/v1/chat/conversations/{conversation_id}", headers=auth(other)).status_code == 404


def test_conversaciones_cuando_borrar_entonces_desaparece(client, user, fake_llm):
    _save(client, user)
    client.post("/api/v1/chat", json={"message": "uno"}, headers=auth(user))
    conversations = client.get("/api/v1/chat/conversations", headers=auth(user)).json()
    assert len(conversations) == 1
    assert client.delete(f"/api/v1/chat/conversations/{conversations[0]['id']}", headers=auth(user)).status_code == 204
    assert client.get("/api/v1/chat/conversations", headers=auth(user)).json() == []


def test_chat_cuando_proveedor_desactivado_entonces_409(client, user):
    _save(client, user, enabled=False)
    res = client.post("/api/v1/chat", json={"message": "hola", "provider": "openai"}, headers=auth(user))
    assert res.status_code == 409


# ─── Contexto ────────────────────────────────────────────────────────────────


def test_contexto_cuando_sin_datos_entonces_lo_dice():
    text = format_context({}, date(2026, 10, 16))
    assert "16/10/2026" in text and "no ha sincronizado" in text


def test_contexto_cuando_datos_entonces_secciones_con_formato_es():
    data = {
        "profile": {"age": 41, "sex": "male", "weight_kg": 72.5, "height_cm": None},
        "summary": {
            "readiness": {"title": "Fresco", "message": "Buen momento.", "acwr": 1.12},
            "fitness": {"ctl": 15.24, "atl": 21.0, "tsb": -5.8},
            "form_label": "Equilibrado",
            "this_week": {"distance_m": 12780, "duration_s": 6113, "count": 2, "load": 93},
            "last_week": {"distance_m": 14000, "duration_s": 6800, "count": 2, "load": 110},
            "planned_this_week": [{"day": "2026-10-13", "title": "Series", "sport": "running", "compliance_score": 92}],
        },
        "activities": [
            {
                "day": "2026-10-14",
                "sport": "running",
                "name": "Rodaje",
                "distance_m": 6010,
                "duration_s": 2570,
                "avg_hr": 148,
            }
        ],  # fmt: skip
        "goals": [
            {
                "name": "10K",
                "distance_m": 10000,
                "race_date": "2026-12-31",
                "days_left": 76,
                "target_time_s": 3720,
                "probable_s": 4131,
                "result_time_s": None,
            }
        ],  # fmt: skip
    }
    text = format_context(data, date(2026, 10, 16))
    assert "41 años, hombre, 72,5 kg" in text
    assert "frescura (TSB) -5,8" in text and "ACWR): 1,12" in text
    assert "Series (running) — cumplimiento 92 %" in text
    assert "6,01 km, 42:50, ritmo 7:08/km, FC media 148" in text
    assert "objetivo 1:02:00, previsión actual 1:08:51" in text


def test_titulo_conversacion_cuando_largo_entonces_corta_por_palabra():
    title = conversation_title("¿Qué ritmo debería llevar en los rodajes suaves esta semana si quiero mejorar mi 10K?")
    assert len(title) <= 61 and title.endswith("…") and " " not in title[-2:]


# ─── Lista de modelos y validación al guardar ────────────────────────────────


def test_guardar_cuando_modelo_retirado_entonces_400_y_no_se_guarda(client, user, monkeypatch, session: Session):
    def retired(provider, key, model):
        raise LLMError("El modelo no está disponible para tu clave; elige otro en Ajustes.", 404)

    monkeypatch.setattr(ai_api, "check_model", retired)
    res = client.put("/api/v1/ai/providers/gemini", json={"api_key": KEY, "model": "gemini-2.5-flash-lite"},
                     headers=auth(user))  # fmt: skip
    assert res.status_code == 400 and "elige otro" in res.json()["error"]["message"]
    assert session.exec(select(AiProviderConfig)).first() is None


def test_guardar_cuando_cambia_modelo_entonces_lo_comprueba_con_la_clave_guardada(client, user, _model_ok):
    _save(client, user)
    _save(client, user, api_key=None, model="gpt-5")
    assert _model_ok[-1] == ("openai", KEY, "gpt-5")


def test_guardar_cuando_solo_cambia_predeterminado_entonces_no_llama_al_proveedor(client, user, _model_ok):
    _save(client, user)
    calls = len(_model_ok)
    _save(client, user, api_key=None, is_default=True)
    assert len(_model_ok) == calls


def test_modelos_cuando_clave_nueva_entonces_recomendados_primero(client, user, monkeypatch):
    seen = []
    monkeypatch.setattr(
        ai_api, "list_models",
        lambda provider, key: seen.append(key) or ["gemini-3.5-pro", "gemini-3.5-flash", "gemini-flash-latest"],
    )  # fmt: skip
    res = client.post("/api/v1/ai/providers/gemini/models", json={"api_key": KEY}, headers=auth(user))
    assert res.json() == {"models": ["gemini-3.5-pro"], "recommended": ["gemini-3.5-flash", "gemini-flash-latest"]}
    assert seen == [KEY]


def test_modelos_cuando_sin_clave_ni_cuenta_entonces_422(client, user):
    assert client.post("/api/v1/ai/providers/gemini/models", json={}, headers=auth(user)).status_code == 422


def test_modelos_cuando_cuenta_guardada_entonces_usa_su_clave(client, user, monkeypatch):
    _save(client, user)
    monkeypatch.setattr(ai_api, "list_models", lambda provider, key: ["gpt-5-mini"] if key == KEY else [])
    res = client.post("/api/v1/ai/providers/openai/models", json={}, headers=auth(user))
    assert res.json()["recommended"] == ["gpt-5-mini"]
