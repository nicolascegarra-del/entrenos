"""Oura simulado con `httpx.MockTransport` (nunca se llama a la API real) y documentos de ejemplo."""

import uuid
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
from sqlmodel import Session

from app.core.config import get_settings
from app.core.crypto import encrypt_secret
from app.core.security import create_token
from app.models import OuraConnection, User
from app.services import oura_client

DAY = date(2026, 10, 20)
CLIENT_SECRET = "secreto-de-prueba"


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


class FakeOura:
    """Responde como la API v2 de Oura con lo que el test le cargue."""

    def __init__(self) -> None:
        self.collections: dict[str, list[dict]] = {}
        self.documents: dict[tuple[str, str], dict] = {}
        self.personal = {"id": "oura-1", "age": 40, "weight": 70.5, "height": 1.78, "biological_sex": "male"}
        self.tokens: list[tuple[int, dict]] = []  # respuestas de /oauth/token en cola
        self.fail: dict[str, list[int]] = {}  # ruta → estados a devolver antes de responder bien
        self.page_size: int | None = None
        self.subscriptions: list[dict] = []
        self.requests: list[httpx.Request] = []
        self.waits: list[float] = []  # esperas entre reintentos (no se duerme de verdad)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if self.fail.get(path):
            return httpx.Response(self.fail[path].pop(0), headers={"retry-after": "0"}, json={})
        if path == "/oauth/token":
            status, body = self.tokens.pop(0) if self.tokens else (200, {
                "access_token": "at-nuevo", "refresh_token": "rt-nuevo", "expires_in": 86400,
                "scope": "email personal daily heartrate workout tag session spo2 heart_health",
            })  # fmt: skip
            return httpx.Response(status, json=body)
        if path == "/oauth/revoke":
            return httpx.Response(200, json={})
        if path == "/v2/usercollection/personal_info":
            return httpx.Response(200, json=self.personal)
        if path.startswith("/v2/webhook/subscription"):
            return self._webhooks(request)
        parts = path.removeprefix("/v2/usercollection/").split("/")
        if len(parts) == 2:
            doc = self.documents.get((parts[0], parts[1]))
            return httpx.Response(200, json=doc) if doc else httpx.Response(404, json={"detail": "no"})
        data = self.collections.get(parts[0], [])
        start = int(request.url.params.get("next_token") or 0)
        size = self.page_size or len(data) or 1
        page = data[start : start + size]
        token = str(start + size) if start + size < len(data) else None
        return httpx.Response(200, json={"data": page, "next_token": token})

    def _webhooks(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("x-client-secret") != CLIENT_SECRET:
            return httpx.Response(401, json={})
        path = request.url.path
        if request.method == "GET":
            return httpx.Response(200, json=self.subscriptions)
        if request.method == "POST":
            import json

            body = json.loads(request.content)
            sub = {"id": str(uuid.uuid4()), "callback_url": body["callback_url"], "event_type": body["event_type"],
                   "data_type": body["data_type"],
                   "expiration_time": (datetime.now(UTC) + timedelta(days=30)).isoformat()}  # fmt: skip
            self.subscriptions.append(sub)
            return httpx.Response(201, json=sub)
        if request.method == "PUT" and "/renew/" in path:
            sub_id = path.rsplit("/", 1)[-1]
            sub = next(s for s in self.subscriptions if s["id"] == sub_id)
            sub["expiration_time"] = (datetime.now(UTC) + timedelta(days=60)).isoformat()
            return httpx.Response(200, json=sub)
        return httpx.Response(405, json={})

    def form(self, index: int = -1) -> dict:
        token_requests = [r for r in self.requests if r.url.path == "/oauth/token"]
        return {k: v[0] for k, v in parse_qs(token_requests[index].content.decode()).items()}


@pytest.fixture
def oura(monkeypatch) -> FakeOura:
    fake = FakeOura()
    monkeypatch.setattr(oura_client, "TRANSPORT", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(oura_client, "sleep", fake.waits.append)
    monkeypatch.setattr(get_settings(), "oura_client_id", "cliente-de-prueba")
    monkeypatch.setattr(get_settings(), "oura_client_secret", CLIENT_SECRET)
    monkeypatch.setattr(get_settings(), "oura_webhook_token", "token-verificacion")
    return fake


@pytest.fixture
def queued(monkeypatch) -> list[tuple[str, list]]:
    """Tareas de Oura encoladas (no se ejecutan)."""
    from app.tasks import oura as tasks

    calls: list[tuple[str, list]] = []
    for name in ("oura_import_history_task", "oura_fetch_object_task", "oura_sync_user_task"):
        task = getattr(tasks, name)
        monkeypatch.setattr(task, "apply_async", lambda args, argsrepr=None, _n=name: calls.append((_n, args)))
    return calls


def connect(session: Session, user: User, expires_in: timedelta = timedelta(hours=12)) -> OuraConnection:
    conn = OuraConnection(
        user_id=user.id, oura_user_id="oura-1", access_token_enc=encrypt_secret("at-viejo"),
        refresh_token_enc=encrypt_secret("rt-viejo"), expires_at=datetime.now(UTC) + expires_in,
        scopes="daily heartrate", history_status="done",
    )  # fmt: skip
    session.add(conn)
    session.commit()
    return conn


# ─── Documentos de ejemplo (formato de la OpenAPI v2 1.42) ───────────────────


def sleep_doc(day: date = DAY, kind: str = "long_sleep", total: int = 27000, doc_id: str = "s-1",
              start: str = "2026-10-19T23:30:00+02:00") -> dict:  # fmt: skip
    return {
        "id": doc_id, "day": day.isoformat(), "type": kind, "bedtime_start": start,
        "bedtime_end": "2026-10-20T07:30:00+02:00", "total_sleep_duration": total, "deep_sleep_duration": 5400,
        "rem_sleep_duration": 6300, "light_sleep_duration": 15300, "awake_time": 1800, "latency": 600,
        "efficiency": 92, "time_in_bed": 28800, "restless_periods": 210, "average_breath": 14.5,
        "average_heart_rate": 52.1, "lowest_heart_rate": 46, "average_hrv": 58, "period": 0,
        "heart_rate": {"interval": 300.0, "items": [55, None, 50, 48, 47, 49], "timestamp": start},
        "hrv": {"interval": 300.0, "items": [40, 55, 60, None, 62, 58], "timestamp": start},
        "movement_30_sec": "1112111", "sleep_phase_5_min": "4221133214", "sleep_phase_30_sec": "42211",
        "readiness": None, "readiness_score_delta": None, "sleep_score_delta": None, "app_sleep_phase_5_min": None,
    }  # fmt: skip


def daily_docs(day: date = DAY) -> dict[str, list[dict]]:
    d = day.isoformat()
    return {
        "daily_sleep": [{"id": "ds-1", "day": d, "score": 82, "timestamp": f"{d}T00:00:00+02:00",
                         "contributors": {"deep_sleep": 90, "efficiency": 88, "latency": 70, "rem_sleep": 85,
                                          "restfulness": 60, "timing": 80, "total_sleep": 77}}],
        "daily_readiness": [{"id": "dr-1", "day": d, "score": 76, "temperature_deviation": -0.21,
                             "temperature_trend_deviation": 0.05, "timestamp": f"{d}T00:00:00+02:00",
                             "contributors": {"activity_balance": 80, "body_temperature": 98, "hrv_balance": 70,
                                              "previous_day_activity": 85, "previous_night": 75,
                                              "recovery_index": 66, "resting_heart_rate": 90,
                                              "sleep_balance": 81, "sleep_regularity": 72}}],
        "daily_activity": [{"id": "da-1", "day": d, "score": 88, "steps": 11200, "active_calories": 650,
                            "total_calories": 2700, "high_activity_time": 1800, "medium_activity_time": 3600,
                            "low_activity_time": 10800, "sedentary_time": 30000, "non_wear_time": 600,
                            "resting_time": 28000, "high_activity_met_minutes": 60, "medium_activity_met_minutes": 120,
                            "low_activity_met_minutes": 200, "sedentary_met_minutes": 20, "inactivity_alerts": 2,
                            "equivalent_walking_distance": 9800, "average_met_minutes": 1.6,
                            "timestamp": f"{d}T04:00:00+02:00", "class_5_min": "0011223344",
                            "met": {"interval": 60.0, "items": [0.9, 1.2, 3.5], "timestamp": f"{d}T04:00:00+02:00"},
                            "contributors": {"meet_daily_targets": 60, "move_every_hour": 100, "recovery_time": 95,
                                             "stay_active": 80, "training_frequency": 100, "training_volume": 90},
                            "meters_to_target": 0, "target_calories": 500, "target_meters": 8000}],
        "daily_spo2": [{"id": "sp-1", "day": d, "spo2_percentage": {"average": 96.8},
                        "breathing_disturbance_index": 4}],
        "daily_stress": [{"id": "st-1", "day": d, "stress_high": 3600, "recovery_high": 5400,
                          "day_summary": "normal"}],
        "daily_resilience": [{"id": "re-1", "day": d, "level": "solid",
                              "contributors": {"sleep_recovery": 70, "daytime_recovery": 55, "stress": 60}}],
        "vO2_max": [{"id": "v-1", "day": d, "timestamp": f"{d}T08:00:00+02:00", "vo2_max": 51.0}],
        "daily_cardiovascular_age": [{"id": "ca-1", "day": d, "vascular_age": 35, "pulse_wave_velocity": 6.9}],
        "sleep_time": [{"id": "stm-1", "day": d, "recommendation": "follow_optimal_bedtime", "status": "optimal_found",
                        "optimal_bedtime": {"day_tz": 7200, "start_offset": -3600, "end_offset": 0}}],
    }  # fmt: skip


def workout_doc(start: datetime, minutes: int = 45, doc_id: str = "w-1", activity: str = "running") -> dict:
    return {"id": doc_id, "activity": activity, "calories": 450.0, "day": start.date().isoformat(),
            "distance": 9000.0, "start_datetime": start.isoformat(),
            "end_datetime": (start + timedelta(minutes=minutes)).isoformat(), "intensity": "moderate",
            "label": None, "source": "autodetected"}  # fmt: skip
