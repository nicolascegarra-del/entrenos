"""Tests de rendimiento: protocolos, alta manual, marcar una actividad como test y confirmar."""

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.models import Activity, PerformanceTest, UserProfile
from app.services import performance_tests as pt

router = APIRouter(tags=["tests de rendimiento"])

_NOT_FOUND = {404: {"description": "No existe o no es tuyo."}}


class TestOut(BaseModel):
    id: int
    sport: str
    protocol: str
    protocol_label: str
    test_date: date
    activity_id: int | None
    activity_name: str | None = None
    source: str
    status: str
    confidence: str
    results: dict
    checks: list[dict]
    notes: str
    summary: str
    created_at: datetime
    confirmed_at: datetime | None


SPORT_PATTERN = "^(running|cycling|swimming)$"


class ManualIn(BaseModel):
    """Resultado conocido (`manual`), informe de laboratorio (`lab`) o tiempos de CSS (`swim_css`)."""

    protocol: str = Field(default="manual", pattern="^(manual|lab|swim_css)$")
    sport: str = Field(pattern=SPORT_PATTERN)
    test_date: date
    lthr: int | None = Field(default=None, ge=100, le=210)
    threshold_pace_s_km: int | None = Field(default=None, ge=150, le=600)
    vo2max: float | None = Field(default=None, ge=20, le=90)
    hr_max: int | None = Field(default=None, ge=120, le=230)
    ftp: int | None = Field(default=None, ge=50, le=600)
    vt1_hr: int | None = Field(default=None, ge=80, le=210)
    vt1_pace_s_km: int | None = Field(default=None, ge=150, le=700)
    vt1_power: int | None = Field(default=None, ge=30, le=600)
    vt2_hr: int | None = Field(default=None, ge=100, le=210)
    vt2_pace_s_km: int | None = Field(default=None, ge=150, le=600)
    vt2_power: int | None = Field(default=None, ge=50, le=600)
    t400_s: float | None = Field(default=None, ge=150, le=1500)
    t200_s: float | None = Field(default=None, ge=70, le=800)
    notes: str = Field(default="", max_length=500)


class LactateStepIn(BaseModel):
    lactate: float = Field(ge=0.3, le=25)
    pace_s_km: int | None = Field(default=None, ge=120, le=900)
    power: int | None = Field(default=None, ge=20, le=1000)
    hr: int | None = Field(default=None, ge=50, le=230)
    lap_index: int | None = Field(default=None, ge=0, description="Tomar ritmo/potencia y FC de esta vuelta")


class LactateIn(BaseModel):
    sport: str = Field(pattern="^(running|cycling)$")
    test_date: date
    activity_id: int | None = None
    steps: list[LactateStepIn] = Field(min_length=4, max_length=20)
    notes: str = Field(default="", max_length=500)


class TestPrefs(BaseModel):
    lactate_tests: bool = True


class MarkIn(BaseModel):
    protocol: str = Field(min_length=1, max_length=32)


def _out(session: SessionDep, row: PerformanceTest) -> TestOut:
    activity = session.get(Activity, row.activity_id) if row.activity_id else None
    protocol = pt.PROTOCOLS.get(row.protocol)
    return TestOut(
        **row.model_dump(exclude={"user_id", "planned_session_id"}),
        protocol_label=protocol.label if protocol else row.protocol,
        activity_name=activity.name if activity else None,
        summary=pt.summary_text(row),
    )


def _own_test(session: SessionDep, user_id: int, test_id: int) -> PerformanceTest:
    row = session.get(PerformanceTest, test_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test no encontrado.")
    return row


@router.get("/tests/protocols", summary="Tipos de test: qué sacan, cómo se hacen y su plantilla para el plan")
def list_protocols(user: CurrentUser) -> list[dict]:
    return pt.protocols_out()


@router.get("/tests", summary="Tus tests, del más reciente al más antiguo")
def list_tests(session: SessionDep, user: CurrentUser) -> list[TestOut]:
    return [_out(session, t) for t in pt.user_tests(session, user.id)]


@router.post(
    "/tests",
    summary="Meter a mano un resultado conocido (queda confirmado y se aplica)",
    status_code=status.HTTP_201_CREATED,
    responses={422: {"description": "Valores fuera de rango o ninguno"}},
)
def create_manual(body: ManualIn, session: SessionDep, user: CurrentUser) -> TestOut:
    if body.test_date > date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "La fecha no puede ser futura.")
    try:
        row = pt.manual_test(session, user.id, body.sport, body.test_date, body.model_dump(), body.notes, body.protocol)
    except pt.TestError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _out(session, row)


@router.post(
    "/tests/lactate",
    summary="Test de lactato escalonado: LT1, LT2 (Dmax modificado u OBLA 4 mmol) y zonas",
    status_code=status.HTTP_201_CREATED,
    responses={422: {"description": "Escalones insuficientes o sin umbral"}},
)
def create_lactate(body: LactateIn, session: SessionDep, user: CurrentUser) -> TestOut:
    if body.test_date > date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "La fecha no puede ser futura.")
    activity = None
    if body.activity_id is not None:
        activity = session.get(Activity, body.activity_id)
        if activity is None or activity.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Actividad no encontrada.")
    try:
        row = pt.lactate_test(
            session, user.id, body.sport, body.test_date, [s.model_dump() for s in body.steps], body.notes, activity
        )
    except pt.TestError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _out(session, row)


@router.get("/tests/preferences", summary="Preferencias de los tests (p. ej. si haces lactato)")
def get_test_prefs(session: SessionDep, user: CurrentUser) -> TestPrefs:
    profile = session.get(UserProfile, user.id)
    return TestPrefs(lactate_tests=profile.lactate_tests if profile else True)


@router.put("/tests/preferences", summary="Guardar las preferencias de los tests")
def put_test_prefs(body: TestPrefs, session: SessionDep, user: CurrentUser) -> TestPrefs:
    profile = session.get(UserProfile, user.id) or UserProfile(user_id=user.id)
    profile.lactate_tests = body.lactate_tests
    session.add(profile)
    session.commit()
    return body


@router.get("/activities/{activity_id}/test", summary="Test de esta actividad (si se marcó como test)")
def get_activity_test(activity_id: int, session: SessionDep, user: CurrentUser) -> TestOut | None:
    activity = session.get(Activity, activity_id)
    if activity is None or activity.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Actividad no encontrada.")
    row = session.exec(select(PerformanceTest).where(PerformanceTest.activity_id == activity_id)).first()
    return _out(session, row) if row else None


@router.post(
    "/activities/{activity_id}/test",
    summary="Marcar la actividad como test y detectar sus valores",
    responses={
        **_NOT_FOUND,
        409: {"description": "Ya tiene un test confirmado"},
        422: {"description": "Protocolo no válido"},
    },
)
def mark_activity_test(activity_id: int, body: MarkIn, session: SessionDep, user: CurrentUser) -> TestOut:
    activity = session.get(Activity, activity_id)
    if activity is None or activity.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Actividad no encontrada.")
    try:
        row = pt.test_from_activity(session, activity, body.protocol)
    except pt.TestError as exc:
        code = status.HTTP_409_CONFLICT if "confirmado" in str(exc) else status.HTTP_422_UNPROCESSABLE_CONTENT
        raise HTTPException(code, str(exc)) from exc
    return _out(session, row)


@router.post(
    "/tests/{test_id}/confirm",
    summary="Aplicar el test a tus zonas (manda 8 semanas sobre Garmin y las estimaciones)",
    responses={**_NOT_FOUND, 409: {"description": "El test no tiene valores"}},
)
def confirm_test(test_id: int, session: SessionDep, user: CurrentUser) -> TestOut:
    try:
        row = pt.confirm(session, _own_test(session, user.id, test_id))
    except pt.TestError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _out(session, row)


@router.delete("/tests/{test_id}", summary="Borrar un test", status_code=204, responses=_NOT_FOUND)
def delete_test(test_id: int, session: SessionDep, user: CurrentUser) -> Response:
    row = _own_test(session, user.id, test_id)
    was_confirmed = row.status == "confirmed"
    session.delete(row)
    session.commit()
    if was_confirmed:
        from app.services.zones import refresh_zones

        refresh_zones(session, user.id)  # vuelven a mandar Garmin o las estimaciones
    return Response(status_code=status.HTTP_204_NO_CONTENT)
