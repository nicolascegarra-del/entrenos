"""
Los tests usan una BD Postgres real (`<db>_test`) porque los modelos dependen de
JSONB y ARRAY. Se recrea el esquema en cada sesión de tests y se vacía tras cada test.
"""

import os

import psycopg
import pytest
from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings

_url = make_url(Settings().database_url)
_test_url = _url.set(database=f"{_url.database}_test")
os.environ["DATABASE_URL"] = _test_url.render_as_string(hide_password=False)
os.environ["APP_ENV"] = "test"
os.environ.setdefault("GARMIN_TOKEN_KEY", "dGVzdC1rZXktc29sby1wYXJhLXRlc3RzLTMyYnl0ZXM=")
get_settings.cache_clear()

with psycopg.connect(
    host=_url.host,
    port=_url.port,
    user=_url.username,
    password=_url.password,
    dbname=_url.database,
    autocommit=True,
) as _admin:
    if not _admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (_test_url.database,)).fetchone():
        _admin.execute(f'CREATE DATABASE "{_test_url.database}"')

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.db import engine  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402

TEST_EMAIL = "atleta@example.com"
TEST_PASSWORD = "contraseña-de-test-123"


@pytest.fixture(scope="session", autouse=True)
def _schema():
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    from app.services import modules

    modules.invalidate_cache()  # la caché de módulos (Redis) no debe sobrevivir entre tests
    yield
    modules.invalidate_cache()
    with engine.begin() as conn:
        for table in reversed(SQLModel.metadata.sorted_tables):
            conn.execute(table.delete())
    limiter.reset()


@pytest.fixture
def session():
    with Session(engine) as s:
        yield s


@pytest.fixture
def user(session: Session) -> User:
    u = User(email=TEST_EMAIL, password_hash=hash_password(TEST_PASSWORD))
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def outbox(monkeypatch) -> list[dict]:
    """Emails encolados durante el test (no se envía nada). Por defecto, correo y captcha desactivados."""
    from app.tasks import email as email_task

    sent: list[dict] = []

    def fake_apply_async(args, argsrepr=None, kwargsrepr=None):
        to, subject, text, html = args
        assert "token=" not in (argsrepr or "") and to not in (argsrepr or "")  # nada sensible en los logs
        sent.append({"to": to, "subject": subject, "text": text, "html": html})

    monkeypatch.setattr(email_task.send_email_task, "apply_async", fake_apply_async)
    monkeypatch.setattr(get_settings(), "email_backend", "disabled")
    # Sin captcha salvo que el test lo active (no depender de las claves del .env local).
    monkeypatch.setattr(get_settings(), "turnstile_site_key", "")
    monkeypatch.setattr(get_settings(), "turnstile_secret_key", "")
    return sent


@pytest.fixture
def mail_on(monkeypatch, outbox) -> list[dict]:
    """Activa el correo (backend de fichero) y devuelve la bandeja de salida."""
    monkeypatch.setattr(get_settings(), "email_backend", "file")
    return outbox
