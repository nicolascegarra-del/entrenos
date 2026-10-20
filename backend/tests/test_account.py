from datetime import UTC, date, datetime, timedelta

import pytest
from garminconnect import GarminConnectAuthenticationError
from sqlmodel import Session, select

from app.core.security import create_token
from app.models import Activity, GarminCredential, GarminStatus, Invitation, Sex, User, UserProfile, WeightLog
from app.services import garmin_client
from app.services import profile as pf
from app.services.progress import user_thresholds
from app.tasks import garmin_connect as gc


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_token(user.id, 'access')}"}


# ─── Cálculos del perfil ────────────────────────────────────────────────────


def test_tanaka_y_edad_cuando_cumpleanos_entonces_edad_exacta():
    assert pf.tanaka_hr_max(40) == 180
    assert pf.age_on(date(1986, 10, 15), date(2026, 10, 14)) == 39
    assert pf.age_on(date(1986, 10, 15), date(2026, 10, 15)) == 40


@pytest.mark.parametrize(
    ("vo2", "age", "sex", "percentile", "bound"),
    [
        (37.8, 45, Sex.MALE, 50, None),  # mediana exacta de 40–49
        (41.4, 45, Sex.MALE, 62, None),  # a medio camino entre P50 (37,8) y P75 (45,0)
        (20.0, 45, Sex.MALE, 5, "below"),
        (60.0, 45, Sex.MALE, 95, "above"),
        (30.2, 35, Sex.FEMALE, 50, None),
    ],
)
def test_vo2max_percentile_cuando_valores_friend_entonces_percentil(vo2, age, sex, percentile, bound):
    result = pf.vo2max_percentile(vo2, age, sex)
    assert result["percentile"] == percentile and result["bound"] == bound


def test_vo2max_percentile_cuando_edad_fuera_de_tabla_entonces_decada_mas_cercana():
    result = pf.vo2max_percentile(24.4, 85, Sex.MALE)
    assert result["age_group"] == "70–79" and result["percentile"] == 50 and result["out_of_range_age"]


def test_age_grade_cuando_hombre_45_10k_en_50_min_entonces_57_por_ciento():
    result = pf.age_grade(10000, 3000, 45, Sex.MALE)
    assert result["factor"] == 0.9261
    assert result["age_standard_s"] == round(1584 / 0.9261)
    assert result["percent"] == pytest.approx(57.0, abs=0.1)
    assert result["level"] == "Corredor popular"


def test_age_grade_cuando_marca_de_record_entonces_100_y_distancia_rara_none():
    assert pf.age_grade(42195, 7235, 30, Sex.MALE)["percent"] == pytest.approx(100, abs=0.5)
    assert pf.age_grade(15000, 3600, 40, Sex.MALE) is None


def test_calories_cuando_carrera_entonces_ecuacion_acsm_y_resto_met():
    # 10 km en 50 min, 70 kg: v = 200 m/min → VO2 = 43,5 ml/kg/min → 15,2 kcal/min × 50
    assert pf.calories("running", 3000, 70, 10000) == 761
    assert pf.calories("strength_training", 3600, 70) == 245  # MET 3,5
    assert pf.calories("strength_training", 3600, 70, rpe=8) == 420  # MET 6,0 (vigoroso)


def test_bmi_cuando_70_kg_y_175_cm_entonces_22_9():
    assert pf.bmi(70, 175) == 22.9


def test_profile_from_garmin_cuando_gramos_entonces_kg():
    garmin = {"userData": {"birthDate": "1986-03-04", "gender": "MALE", "weight": 72500.0, "height": 178.0}}
    assert pf.profile_from_garmin(garmin) == {
        "birth_date": date(1986, 3, 4), "sex": Sex.MALE, "weight_kg": 72.5, "height_cm": 178.0,
    }  # fmt: skip
    assert pf.profile_from_garmin({"userData": {"birthDate": "no-es-fecha"}}) == {}


def test_apply_garmin_profile_cuando_editado_a_mano_entonces_solo_rellena_vacios(session: Session, user: User):
    session.add(UserProfile(user_id=user.id, weight_kg=70.0, source="manual"))
    session.commit()
    garmin = {"userData": {"birthDate": "1986-03-04", "gender": "MALE", "weight": 80000.0, "height": 178.0}}
    profile = pf.apply_garmin_profile(session, user.id, garmin)
    assert profile.weight_kg == 70.0  # no pisa lo editado
    assert profile.birth_date == date(1986, 3, 4) and profile.height_cm == 178.0
    assert profile.source == "manual"


def test_apply_garmin_profile_cuando_sin_editar_entonces_actualiza_y_guarda_peso(session: Session, user: User):
    profile = pf.apply_garmin_profile(session, user.id, {"userData": {"weight": 75000.0, "gender": "FEMALE"}})
    assert profile.source == "garmin" and profile.sex == Sex.FEMALE
    log = session.exec(select(WeightLog).where(WeightLog.user_id == user.id)).one()
    assert log.weight_kg == 75.0 and log.source == "garmin"


def test_thresholds_cuando_sin_fc_max_registrada_entonces_tanaka(session: Session, user: User):
    session.add(UserProfile(user_id=user.id, birth_date=date.today().replace(year=date.today().year - 40)))
    session.commit()
    t = user_thresholds(session, user.id)
    assert t.hr_max == 180 and t.lthr == round(180 * 0.89)


# ─── Tokens cifrados ────────────────────────────────────────────────────────


def test_tokens_cuando_se_guardan_entonces_cifrados_y_recuperables(session: Session, user: User):
    garmin_client.save_tokens(session, user.id, '{"di_token": "secreto"}', "Nico")
    credential = session.get(GarminCredential, user.id)
    assert "secreto" not in credential.tokens_enc
    assert garmin_client.decrypt_tokens(credential.tokens_enc) == '{"di_token": "secreto"}'
    assert garmin_client.has_tokens(user.id) is True
    credential.status = GarminStatus.EXPIRED
    session.add(credential)
    session.commit()
    assert garmin_client.has_tokens(user.id) is False


def test_tokens_cuando_fichero_antiguo_entonces_se_migran_a_la_bd_y_se_borra(session, user, tmp_path, monkeypatch):
    settings = type(
        "S", (), {"garmin_token_dir": str(tmp_path), "garmin_token_key": garmin_client.get_settings().garmin_token_key}
    )
    monkeypatch.setattr(garmin_client, "get_settings", lambda: settings)
    (tmp_path / str(user.id)).mkdir()
    (tmp_path / str(user.id) / "garmin_tokens.json").write_text('{"di_token": "viejo"}')
    assert garmin_client.has_tokens(user.id) is True
    assert not (tmp_path / str(user.id)).exists()
    session.expire_all()
    assert garmin_client.decrypt_tokens(session.get(GarminCredential, user.id).tokens_enc) == '{"di_token": "viejo"}'


# ─── Conexión con MFA (Garmin y Redis simulados) ────────────────────────────


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict = {}

    def hset(self, key, mapping):
        self.data.setdefault(key, {}).update(mapping)

    def hgetall(self, key):
        return dict(self.data.get(key, {}))

    def expire(self, key, ttl):
        pass

    def set(self, key, value, ex=None):
        self.data[key] = value

    def getdel(self, key):
        return self.data.pop(key, None)


class FakeGarminApi:
    """Simula el cliente de garminconnect: pide MFA si `mfa` y valida la contraseña."""

    def __init__(self, email, password, prompt_mfa, mfa=False):
        self.email, self.password, self.prompt_mfa, self.mfa = email, password, prompt_mfa, mfa
        self.full_name = "Atleta de prueba"
        self.received_code = None
        self.client = type("C", (), {"dumps": staticmethod(lambda: '{"di_token": "nuevo"}')})()

    def login(self):
        if self.password != "correcta":
            raise GarminConnectAuthenticationError("bad credentials")
        if self.mfa:
            self.received_code = self.prompt_mfa()

    def get_user_profile(self):
        return {"userData": {"gender": "MALE", "weight": 70000.0, "birthDate": "1990-01-01", "height": 175.0}}


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(gc, "_redis", lambda: fake)
    return fake


def test_run_connect_cuando_credenciales_ok_entonces_guarda_tokens_y_perfil(session, user, fake_redis):
    gc.set_state("c1", user_id=user.id, status=gc.PENDING)
    password_enc = garmin_client.encrypt_tokens("correcta")
    assert gc.run_connect("c1", user.id, "a@b.c", password_enc, api_factory=FakeGarminApi) == gc.CONNECTED
    assert gc.get_state("c1")["status"] == "connected"
    credential = session.get(GarminCredential, user.id)
    assert credential.display_name == "Atleta de prueba"
    assert session.get(UserProfile, user.id).weight_kg == 70.0


def test_run_connect_cuando_garmin_pide_codigo_entonces_lo_espera_y_lo_usa(session, user, fake_redis):
    apis: list[FakeGarminApi] = []

    def factory(**kwargs):
        apis.append(FakeGarminApi(mfa=True, **kwargs))
        return apis[-1]

    gc.set_state("c2", user_id=user.id, status=gc.PENDING)
    gc.submit_mfa_code("c2", "123456")  # el usuario ya lo ha enviado
    password_enc = garmin_client.encrypt_tokens("correcta")
    assert gc.run_connect("c2", user.id, "a@b.c", password_enc, api_factory=factory) == gc.CONNECTED
    assert apis[0].received_code == "123456"


def test_run_connect_cuando_contrasena_mala_entonces_error_legible_sin_tokens(session, user, fake_redis):
    gc.set_state("c3", user_id=user.id, status=gc.PENDING)
    password_enc = garmin_client.encrypt_tokens("mala")
    assert gc.run_connect("c3", user.id, "a@b.c", password_enc, api_factory=FakeGarminApi) == gc.ERROR
    state = gc.get_state("c3")
    assert state["status"] == "error" and "incorrectos" in state["error"]
    assert session.get(GarminCredential, user.id) is None


def test_api_connect_cuando_flujo_entonces_estado_mfa_y_propiedad(client, session, user, fake_redis, monkeypatch):
    queued = []
    monkeypatch.setattr(gc.connect_task, "delay", lambda *args: queued.append(args))
    res = client.post("/api/v1/garmin/connect", json={"email": "a@b.c", "password": "x"}, headers=auth(user))
    assert res.status_code == 202
    connect_id = res.json()["connect_id"]
    assert queued and "x" not in queued[0]  # la contraseña viaja cifrada
    assert client.get(f"/api/v1/garmin/connect/{connect_id}", headers=auth(user)).json()["status"] == "pending"
    assert client.post(f"/api/v1/garmin/connect/{connect_id}/mfa", json={"code": "123456"},
                       headers=auth(user)).status_code == 409  # fmt: skip
    gc.set_state(connect_id, status=gc.NEEDS_MFA)
    assert client.post(f"/api/v1/garmin/connect/{connect_id}/mfa", json={"code": "123456"},
                       headers=auth(user)).json()["status"] == "verifying"  # fmt: skip
    other = User(email="otra@example.com", password_hash="x")
    session.add(other)
    session.commit()
    assert client.get(f"/api/v1/garmin/connect/{connect_id}", headers=auth(other)).status_code == 404


def test_api_disconnect_cuando_conectado_entonces_borra_tokens(client, session, user):
    garmin_client.save_tokens(session, user.id, "{}")
    assert client.delete("/api/v1/garmin/connection", headers=auth(user)).status_code == 204
    session.expire_all()
    assert session.get(GarminCredential, user.id) is None


# ─── Perfil (API) ───────────────────────────────────────────────────────────


def test_api_profile_cuando_se_edita_entonces_calculos_y_peso(client, session, user):
    metrics = {"vo2max": 44.0, "avg_stride_length": 89.0}
    session.add(Activity(user_id=user.id, sport="running", start_time=datetime.now(UTC), duration_s=3000,
                         distance_m=10000, max_hr=185, metrics=metrics))  # fmt: skip
    session.commit()
    body = {"birth_date": "1986-03-04", "sex": "male", "weight_kg": 70, "height_cm": 178}
    res = client.put("/api/v1/profile", json=body, headers=auth(user)).json()
    assert res["source"] == "manual" and res["age"] == pf.age_on(date(1986, 3, 4), date.today())
    assert res["hr_max"] == 185 and res["hr_max_source"] == "real"
    assert res["bmi"] == 22.1 and res["stride_ratio"] == 0.5
    assert res["vo2max_percentile"]["age_group"] in ("30–39", "40–49")
    assert res["weight_history"][0]["weight_kg"] == 70


def test_api_profile_cuando_fecha_imposible_entonces_422(client, user):
    res = client.put("/api/v1/profile", json={"birth_date": "2025-01-01"}, headers=auth(user))
    assert res.status_code == 422 and "nacimiento" in res.json()["error"]["message"]


def test_api_records_cuando_perfil_entonces_ajuste_por_edad(client, session, user):
    session.add(UserProfile(user_id=user.id, birth_date=date(1980, 1, 1), sex=Sex.MALE))
    session.add(Activity(user_id=user.id, sport="running", start_time=datetime.now(UTC), duration_s=3000,
                         distance_m=10000, metrics={"best_10k": 3000.0}))  # fmt: skip
    session.commit()
    records = {r["key"]: r for r in client.get("/api/v1/progress/records", headers=auth(user)).json()}
    assert records["best_10k"]["age_grade"]["percent"] > 50


# ─── Invitaciones y alta de usuarios ────────────────────────────────────────


@pytest.fixture
def admin(session: Session) -> User:
    a = User(email="admin@example.com", password_hash="x", is_admin=True)
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def _token(link: str) -> str:
    return link.split("token=", 1)[1]


def test_invitations_cuando_no_admin_entonces_403(client, user):
    res = client.post("/api/v1/admin/invitations", json={"email": "n@example.com"}, headers=auth(user))
    assert res.status_code == 403
    assert client.get("/api/v1/admin/users", headers=auth(user)).status_code == 403


def test_invitacion_cuando_flujo_completo_entonces_usuario_creado_y_logueado(client, session, admin):
    inv = client.post("/api/v1/admin/invitations", json={"email": "Nueva@Example.com"}, headers=auth(admin)).json()
    token = _token(inv["link"])
    assert inv["email"] == "nueva@example.com" and inv["status"] == "pending" and not inv["emailed"]
    stored = session.exec(select(Invitation)).one()
    assert stored.token_hash != token  # en BD solo el hash
    assert client.get(f"/api/v1/invitations/check?token={token}").json() == {"email": "nueva@example.com"}
    res = client.post("/api/v1/auth/register", json={"token": token, "password": "una-clave-larga"})
    assert res.status_code == 200 and res.json()["access_token"]
    assert "refresh_token" in res.headers["set-cookie"]
    again = client.post("/api/v1/auth/register", json={"token": token, "password": "una-clave-larga"})
    assert again.status_code == 400  # un solo uso
    users = client.get("/api/v1/admin/users", headers=auth(admin)).json()["items"]
    assert {u["email"] for u in users} == {"admin@example.com", "nueva@example.com"}
    used = client.get("/api/v1/admin/invitations", headers=auth(admin)).json()[0]
    assert used["status"] == "used" and used["used_by_email"] == "nueva@example.com"


def test_invitacion_cuando_caducada_entonces_400(client, session, admin):
    inv = client.post("/api/v1/admin/invitations", json={"email": "tarde@example.com"}, headers=auth(admin)).json()
    stored = session.exec(select(Invitation)).one()
    stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    session.add(stored)
    session.commit()
    res = client.post("/api/v1/auth/register", json={"token": _token(inv["link"]), "password": "una-clave-larga"})
    assert res.status_code == 400 and "caducado" in res.json()["error"]["message"]


def test_invitacion_cuando_email_ya_existe_entonces_409_y_clave_corta_422(client, user, admin):
    res = client.post("/api/v1/admin/invitations", json={"email": user.email}, headers=auth(admin))
    assert res.status_code == 409
    inv = client.post("/api/v1/admin/invitations", json={"email": "otro@example.com"}, headers=auth(admin)).json()
    res = client.post("/api/v1/auth/register", json={"token": _token(inv["link"]), "password": "corta"})
    assert res.status_code == 422


def test_anular_invitacion_cuando_admin_entonces_desaparece(client, admin):
    inv = client.post("/api/v1/admin/invitations", json={"email": "x@example.com"}, headers=auth(admin)).json()
    assert client.delete(f"/api/v1/admin/invitations/{inv['id']}", headers=auth(admin)).status_code == 204
    assert client.get("/api/v1/admin/invitations", headers=auth(admin)).json() == []
