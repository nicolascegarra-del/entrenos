from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.api import ai as ai_api
from app.core.security import create_token
from app.models import Activity, ActivityReview, AiProvider, AiProviderConfig, AiReviewSettings, User
from app.services import activity_review as svc
from app.services.llm import Chunk, LLMError


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def _act(session: Session, user: User, hours_ago: float = 2, sport: str = "running", minutes: int = 40) -> Activity:
    a = Activity(user_id=user.id, sport=sport, name="Rodaje", duration_s=minutes * 60, distance_m=8000,
                 start_time=datetime.now(UTC) - timedelta(hours=hours_ago), avg_hr=148)  # fmt: skip
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def _ai(session: Session, user: User) -> None:
    session.add(AiProviderConfig(user_id=user.id, provider=AiProvider.ANTHROPIC, model="claude-haiku-5-5",
                                 key_enc=ai_api.encrypt_secret("sk-ant-1234567890"), key_last4="7890", enabled=True,
                                 is_default=True))  # fmt: skip
    session.commit()


def _enable(session: Session, user: User, **kw) -> None:
    session.add(AiReviewSettings(user_id=user.id, enabled=True, **kw))
    session.commit()


@pytest.fixture
def queued(monkeypatch):
    ids: list[int] = []
    monkeypatch.setattr(svc, "_enqueue", ids.append)
    return ids


# ─── Cuándo se analiza ───────────────────────────────────────────────────────


def test_desactivado_por_defecto(session, user):
    _ai(session, user)
    assert svc.skip_reason(session, _act(session, user)) == "desactivado"


def test_motivos_para_no_analizar(session, user):
    _enable(session, user, sports=["running", "strength"], daily_max=1)
    assert svc.skip_reason(session, _act(session, user)) == "sin IA"
    _ai(session, user)
    assert svc.skip_reason(session, _act(session, user, sport="cycling")) == "deporte"
    assert svc.skip_reason(session, _act(session, user, minutes=5)) == "corta"
    assert svc.skip_reason(session, _act(session, user, hours_ago=60)) == "antigua"
    assert svc.skip_reason(session, _act(session, user, sport="strength_training")) is None  # fuerza incluida
    ok = _act(session, user)
    assert svc.skip_reason(session, ok) is None
    session.add(ActivityReview(activity_id=ok.id, user_id=user.id))
    session.commit()
    assert svc.skip_reason(session, ok) == "ya analizada"
    assert svc.skip_reason(session, _act(session, user)) == "tope diario"


def test_encola_solo_las_que_tocan(session, user, queued):
    _ai(session, user)
    _enable(session, user)
    start = datetime.now(UTC) - timedelta(seconds=1)
    fresh = _act(session, user)
    _act(session, user, hours_ago=200)  # histórico antiguo importado ahora: no
    ids = svc.queue_reviews(session, user.id, start)
    assert len(ids) == 1 and queued == ids
    review = session.get(ActivityReview, ids[0])
    assert review.activity_id == fresh.id and review.status == "pending"


def test_importar_fichero_lanza_el_analisis(session, user, queued):
    from app.services.file_import import after_import

    _ai(session, user)
    _enable(session, user)
    _act(session, user)
    after_import(session, user.id)
    assert len(queued) == 1


# ─── Generación ──────────────────────────────────────────────────────────────


def test_genera_y_avisa(session, user, monkeypatch):
    _ai(session, user)
    a = _act(session, user)
    review = ActivityReview(activity_id=a.id, user_id=user.id)
    session.add(review)
    session.commit()
    seen, sent = {}, []

    def fake(provider, api_key, model, system, messages, tools=None, executor=None, client=None):
        seen.update(system=system, question=messages[0]["content"], tools=[t.name for t in tools])
        yield Chunk(tool="Tus zonas y umbrales")
        yield Chunk(text="**Cómo ha ido**: rodaje suave a 5:00/km con el pulso en Z2.\n**Qué te aporta**: base.")
        yield Chunk(input_tokens=900, output_tokens=120)

    monkeypatch.setattr(svc, "stream_chat", fake)
    monkeypatch.setattr(svc.notifications, "notify", lambda *args, **kw: sent.append(args) or True)
    out = svc.generate(session, review.id)
    assert out.status == "done" and out.content.startswith("**Cómo ha ido**") and out.tools == ["Tus zonas y umbrales"]
    assert out.input_tokens == 900 and svc.provider_label(out) == "Claude · claude-haiku-5-5"
    assert "**Próximos días**" in seen["system"] and "detalle_actividad" in seen["tools"]
    assert "Detalle de «Rodaje»" in seen["question"]  # datos ya calculados
    assert sent and sent[0][2] == "activity_review" and "rodaje suave a 5:00/km" in sent[0][5]


def test_error_del_proveedor_queda_registrado(session, user, monkeypatch):
    _ai(session, user)
    a = _act(session, user)
    review = ActivityReview(activity_id=a.id, user_id=user.id)
    session.add(review)
    session.commit()

    def failing(*args, **kwargs):
        raise LLMError("Has superado el límite del proveedor o no te queda saldo en la cuenta.", 429)
        yield  # pragma: no cover

    monkeypatch.setattr(svc, "stream_chat", failing)
    out = svc.generate(session, review.id)
    assert out.status == "error" and "saldo" in out.error


# ─── API ─────────────────────────────────────────────────────────────────────


def test_api_pedir_y_ver_el_analisis(client, user, session, queued):
    a = _act(session, user)
    assert client.get(f"/api/v1/activities/{a.id}/review", headers=auth(user)).json() is None
    assert client.post(f"/api/v1/activities/{a.id}/review", headers=auth(user)).status_code == 409
    _ai(session, user)
    res = client.post(f"/api/v1/activities/{a.id}/review", headers=auth(user))
    assert res.status_code == 202 and res.json()["status"] == "pending" and len(queued) == 1
    review = session.exec(select(ActivityReview)).one()
    review.status, review.content = "done", "**Cómo ha ido**: bien."
    session.add(review)
    session.commit()
    got = client.get(f"/api/v1/activities/{a.id}/review", headers=auth(user)).json()
    assert got["status"] == "done" and got["content"].startswith("**Cómo")
    latest = client.get("/api/v1/ai/reviews/latest", headers=auth(user)).json()
    assert latest["activity_name"] == "Rodaje" and latest["activity_id"] == a.id


def test_api_ajustes_del_analisis(client, user, session):
    data = client.get("/api/v1/ai/review-settings", headers=auth(user)).json()
    assert data["enabled"] is False and "strength" in data["sports"] and data["has_ai"] is False
    body = {"enabled": True, "sports": ["running", "strength"], "daily_max": 3}
    data = client.put("/api/v1/ai/review-settings", json=body, headers=auth(user)).json()
    assert data["enabled"] and data["sports"] == ["running", "strength"] and data["daily_max"] == 3
    bad = client.put("/api/v1/ai/review-settings", json={**body, "sports": ["ajedrez"]}, headers=auth(user))
    assert bad.status_code == 422


def test_api_actividad_ajena(client, user, session):
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    a = _act(session, other)
    assert client.get(f"/api/v1/activities/{a.id}/review", headers=auth(user)).status_code == 404
