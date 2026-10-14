from fastapi.testclient import TestClient

from app.api.auth import REFRESH_COOKIE
from app.core.security import create_token
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


def _login(client: TestClient, password: str = TEST_PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": TEST_EMAIL, "password": password})


def test_login_cuando_credenciales_correctas_entonces_devuelve_access_y_cookie_httponly(client, user):
    res = _login(client)
    assert res.status_code == 200
    assert res.json()["access_token"]
    assert res.json()["expires_in"] == 15 * 60
    cookie = res.headers["set-cookie"]
    assert REFRESH_COOKIE in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie


def test_login_cuando_password_incorrecta_entonces_401_formato_klyp(client, user):
    res = _login(client, "mala")
    assert res.status_code == 401
    error = res.json()["error"]
    assert error["code"] == "UNAUTHORIZED"
    assert error["request_id"].startswith("req_")


def test_login_cuando_email_invalido_entonces_422_con_campo(client):
    res = client.post("/api/v1/auth/login", json={"email": "no-es-email", "password": "x"})
    assert res.status_code == 422
    assert res.json()["error"]["field"] == "email"
    assert res.json()["error"]["message"] == "El campo email no es válido."


def test_login_cuando_email_con_mayusculas_y_dominio_test_entonces_ok(client, session):
    from app.core.security import hash_password
    from app.models import User

    session.add(User(email="dev@entrenos.test", password_hash=hash_password(TEST_PASSWORD)))
    session.commit()
    res = client.post("/api/v1/auth/login", json={"email": " Dev@Entrenos.TEST ", "password": TEST_PASSWORD})
    assert res.status_code == 200


def test_login_cuando_supera_5_intentos_por_minuto_entonces_429(client, user):
    codes = [_login(client, "mala").status_code for _ in range(6)]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429


def test_me_cuando_access_token_valido_entonces_devuelve_usuario(client, user):
    token = _login(client).json()["access_token"]
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json() == {"id": user.id, "email": TEST_EMAIL, "is_admin": False}


def test_me_cuando_sin_token_entonces_401(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_cuando_se_usa_refresh_token_entonces_401(client, user):
    token = create_token(user.id, "refresh")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_refresh_cuando_cookie_valida_entonces_emite_nuevo_access(client, user):
    _login(client)
    res = client.post("/api/v1/auth/refresh")
    assert res.status_code == 200
    assert res.json()["access_token"]


def test_refresh_cuando_sin_cookie_entonces_401(client):
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_cuando_cookie_es_access_token_entonces_401(client, user):
    client.cookies.set(REFRESH_COOKIE, create_token(user.id, "access"), path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_cuando_se_llama_entonces_borra_cookie(client, user):
    _login(client)
    res = client.post("/api/v1/auth/logout")
    assert res.status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_health_cuando_bd_disponible_entonces_ok_y_cabeceras_seguridad(client):
    res = client.get("/health")
    assert res.json() == {"status": "ok"}
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
