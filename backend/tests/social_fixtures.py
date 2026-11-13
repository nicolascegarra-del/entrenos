"""Utilidades compartidas por los tests de la parte social (personas, actividades, trazas y avisos)."""

import math
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session

from app.core.security import create_token, hash_password
from app.models import Activity, ActivityStream, Follow, SocialProfile, User
from app.services import notifications

PASSWORD = "contraseña-de-test-123"


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access', user.token_version)}"}


def make_user(
    session: Session,
    handle: str,
    name: str | None = None,
    public: bool = False,
    default_visibility: str = "followers",
    profile: bool = True,
    **extra,
) -> User:
    u = User(email=f"{handle}@example.com", password_hash=hash_password(PASSWORD))
    session.add(u)
    session.commit()
    session.refresh(u)
    if profile:
        session.add(
            SocialProfile(
                user_id=u.id,
                display_name=name or handle.capitalize(),
                handle=handle,
                visibility="public" if public else "private",
                default_activity_visibility=default_visibility,
                **extra,
            )
        )
        session.commit()
    return u


def befriend(session: Session, follower: User, followee: User, status: str = "accepted") -> Follow:
    row = Follow(
        follower_id=follower.id,
        followee_id=followee.id,
        status=status,
        accepted_at=datetime.now(UTC) if status == "accepted" else None,
    )
    session.add(row)
    session.commit()
    return row


def add_activity(
    session: Session,
    user: User,
    start: datetime | None = None,
    distance_m: float = 10_000,
    duration_s: float = 3_000,
    sport: str = "running",
    visibility: str | None = None,
    **extra,
) -> Activity:
    a = Activity(
        user_id=user.id,
        sport=sport,
        name=extra.pop("name", "Rodaje"),
        start_time=start or datetime.now(UTC) - timedelta(hours=1),
        duration_s=duration_s,
        moving_duration_s=extra.pop("moving_duration_s", duration_s),
        distance_m=distance_m,
        visibility=visibility,
        **extra,
    )
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def straight_track(meters: float, step_m: float = 10) -> tuple[list[float], list[float]]:
    """Traza recta hacia el norte desde (40, -3), un punto cada `step_m` metros."""
    deg_per_m = 1 / 111_195.0
    n = int(meters / step_m) + 1
    return [40 + i * step_m * deg_per_m for i in range(n)], [-3.0] * n


def add_track(session: Session, activity: Activity, lats: list[float], lons: list[float]) -> None:
    session.add(ActivityStream(activity_id=activity.id, channel="lat", values=lats))
    session.add(ActivityStream(activity_id=activity.id, channel="lon", values=lons))
    session.add(ActivityStream(activity_id=activity.id, channel="hr", values=[150.0] * len(lats)))
    session.commit()


def distance_from_start(lat: float) -> float:
    return (lat - 40) * 111_195.0 * math.cos(0)


@pytest.fixture
def pushes(monkeypatch) -> list[dict]:
    """Avisos push enviados (simulados como entregados a un dispositivo)."""
    sent: list[dict] = []

    def fake_push(session, user_id, title, body, url="/", tag=None):
        sent.append({"user_id": user_id, "title": title, "body": body, "url": url, "tag": tag})
        return {"sent": 1, "failed": 0}

    monkeypatch.setattr(notifications, "push", fake_push)
    return sent
