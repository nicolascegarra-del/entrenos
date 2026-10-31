from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session

from app.core.security import create_token
from app.models import SyncMode, SyncRun, User, UserSettings
from app.services.sync_schedule import is_due, next_sync_at
from app.tasks import sync as sync_tasks

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


def settings(mode: SyncMode = SyncMode.AUTO, interval: int = 30) -> UserSettings:
    return UserSettings(user_id=1, sync_mode=mode, sync_interval_min=interval)


@pytest.mark.parametrize(
    ("minutes_ago", "interval", "expected"),
    [
        (None, 30, True),  # nunca sincronizado
        (10, 30, False),
        (28, 30, True),  # margen de medio tick (2,5 min) para no ir con retraso
        (45, 60, False),
        (61, 60, True),
    ],
)
def test_is_due_cuando_modo_auto_entonces_respeta_intervalo(minutes_ago, interval, expected):
    last = None if minutes_ago is None else NOW - timedelta(minutes=minutes_ago)
    assert is_due(settings(interval=interval), last, NOW) is expected


def test_is_due_cuando_modo_manual_entonces_nunca():
    assert is_due(settings(SyncMode.MANUAL), None, NOW) is False
    assert next_sync_at(settings(SyncMode.MANUAL), NOW, NOW) is None


def test_next_sync_at_cuando_auto_entonces_ultima_mas_intervalo_o_ahora():
    assert next_sync_at(settings(interval=60), NOW - timedelta(minutes=20), NOW) == NOW + timedelta(minutes=40)
    assert next_sync_at(settings(interval=60), NOW - timedelta(hours=3), NOW) == NOW
    assert next_sync_at(settings(), None, NOW) == NOW


def test_get_sync_settings_cuando_nunca_guardadas_entonces_valores_por_defecto(client, user):
    res = client.get("/api/v1/settings/sync", headers=auth(user)).json()
    assert res["mode"] == "auto" and res["interval_min"] == 240
    assert res["intervals"] == [60, 240, 480, 960, 1440]
    assert res["next_sync_at"] is not None


def test_put_sync_settings_cuando_manual_entonces_sin_proxima(client, session, user):
    res = client.put("/api/v1/settings/sync", json={"mode": "manual", "interval_min": 480}, headers=auth(user))
    assert res.status_code == 200
    assert res.json()["mode"] == "manual" and res.json()["next_sync_at"] is None
    assert session.get(UserSettings, user.id).sync_interval_min == 480


def test_put_sync_settings_cuando_intervalo_no_permitido_entonces_422(client, user):
    res = client.put("/api/v1/settings/sync", json={"mode": "auto", "interval_min": 7}, headers=auth(user))
    assert res.status_code == 422
    assert "60, 240, 480" in res.json()["error"]["message"]


def test_users_due_cuando_varios_usuarios_entonces_solo_auto_con_intervalo_cumplido(session: Session, monkeypatch):
    users = [User(email=f"u{i}@example.com", password_hash="x") for i in range(4)]
    session.add_all(users)
    session.commit()
    auto_due, auto_recent, manual, no_garmin = (u.id for u in users)
    now = datetime.now(UTC)
    session.add_all(
        [
            UserSettings(user_id=auto_due, sync_interval_min=60),
            UserSettings(user_id=auto_recent, sync_interval_min=60),
            UserSettings(user_id=manual, sync_mode=SyncMode.MANUAL),
            SyncRun(user_id=auto_due, started_at=now - timedelta(minutes=90)),
            SyncRun(user_id=auto_recent, started_at=now - timedelta(minutes=10)),
        ]
    )
    session.commit()
    monkeypatch.setattr(sync_tasks, "has_tokens", lambda uid: uid != no_garmin)
    assert sync_tasks.users_due(now) == [auto_due]


def test_connection_due_cuando_auto_manual_o_reciente_entonces_respeta_el_ajuste_general(session: Session, user):
    from app.services.sync_schedule import connection_due

    now = datetime.now(UTC)
    session.add(UserSettings(user_id=user.id, sync_interval_min=240))
    session.commit()
    assert connection_due(session, user.id, None, now)
    assert connection_due(session, user.id, now - timedelta(hours=5), now)
    assert not connection_due(session, user.id, now - timedelta(hours=1), now)
    row = session.get(UserSettings, user.id)
    row.sync_mode = SyncMode.MANUAL
    session.add(row)
    session.commit()
    assert not connection_due(session, user.id, None, now)


def test_devices_sync_all_cuando_no_toca_entonces_no_sincroniza(session: Session, user, monkeypatch):
    import contextlib

    from app.services import devices
    from app.tasks import devices as device_tasks

    session.add(UserSettings(user_id=user.id, sync_interval_min=960))
    devices.save_session(session, user.id, "suunto", {"session_key": "SK"}, "yo")
    conn = devices.get_connection(session, user.id, "suunto")
    conn.last_sync_at = datetime.now(UTC) - timedelta(hours=2)
    session.add(conn)
    session.commit()
    calls: list = []
    monkeypatch.setattr(device_tasks, "Session", lambda _engine: contextlib.nullcontext(session))
    monkeypatch.setattr(devices, "sync", lambda s, uid, p: calls.append(p) or 0)
    device_tasks.devices_sync_all_task()
    assert calls == []  # cada 16 h y hace 2 h: aún no toca
