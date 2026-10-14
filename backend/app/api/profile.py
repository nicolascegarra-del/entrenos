from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from sqlmodel import col, select

from app.api.deps import CurrentUser, SessionDep
from app.models import Activity, Sex, WeightLog
from app.services import profile as svc
from app.services import progress as prog
from app.services.plan_steps import sport_family

router = APIRouter(prefix="/profile", tags=["perfil"])


class ProfileIn(BaseModel):
    birth_date: date | None = None
    sex: Sex | None = None
    weight_kg: float | None = Field(default=None, gt=20, lt=300)
    height_cm: float | None = Field(default=None, gt=100, lt=250)

    @field_validator("birth_date")
    @classmethod
    def plausible_birth_date(cls, value: date | None) -> date | None:
        if value and not 5 <= svc.age_on(value, date.today()) <= 110:
            raise ValueError("La fecha de nacimiento no es válida.")
        return value


class ProfileOut(ProfileIn):
    source: str
    age: int | None
    hr_max: float | None
    hr_max_source: str | None  # real | tanaka
    bmi: float | None
    stride_ratio: float | None  # zancada media / altura
    vo2max: float | None
    vo2max_percentile: dict | None
    weight_history: list[dict]


def _out(session: SessionDep, user_id: int) -> ProfileOut:
    profile = svc.get_profile(session, user_id)
    today = date.today()
    age = svc.age_on(profile.birth_date, today) if profile.birth_date else None
    thresholds = prog.user_thresholds(session, user_id)
    observed_max = max(
        (a.max_hr for a in session.exec(select(Activity).where(Activity.user_id == user_id)).all() if a.max_hr),
        default=None,
    )
    hr_max_source = "real" if observed_max else "tanaka" if age else None

    runs = session.exec(
        select(Activity).where(Activity.user_id == user_id).order_by(col(Activity.start_time).desc()).limit(30)
    ).all()
    strides = [a.metrics["avg_stride_length"] for a in runs if sport_family(a.sport) == "running"
               and a.metrics.get("avg_stride_length")]  # fmt: skip
    stride_ratio = round(sum(strides) / len(strides) / profile.height_cm, 2) if strides and profile.height_cm else None
    vo2 = next((a.metrics["vo2max"] for a in runs if a.metrics.get("vo2max")), None)
    percentile = svc.vo2max_percentile(vo2, age, profile.sex) if vo2 and age and profile.sex else None
    history = session.exec(select(WeightLog).where(WeightLog.user_id == user_id).order_by(WeightLog.day)).all()
    return ProfileOut(
        birth_date=profile.birth_date,
        sex=profile.sex,
        weight_kg=profile.weight_kg,
        height_cm=profile.height_cm,
        source=profile.source,
        age=age,
        hr_max=thresholds.hr_max,
        hr_max_source=hr_max_source,
        bmi=svc.bmi(profile.weight_kg, profile.height_cm) if profile.weight_kg and profile.height_cm else None,
        stride_ratio=stride_ratio,
        vo2max=vo2,
        vo2max_percentile=percentile,
        weight_history=[{"day": w.day, "weight_kg": w.weight_kg} for w in history],
    )


@router.get(
    "",
    summary="Perfil del atleta",
    description="Datos personales y lo que se calcula con ellos: edad, FC máx. (real o Tanaka), IMC, zancada "
    "relativa y percentil de VO2max (FRIEND, Kaminsky 2015).",
)
def get_profile(session: SessionDep, user: CurrentUser) -> ProfileOut:
    return _out(session, user.id)


@router.put("", summary="Editar perfil")
def update_profile(body: ProfileIn, session: SessionDep, user: CurrentUser) -> ProfileOut:
    profile = svc.get_profile(session, user.id)
    if body.weight_kg and body.weight_kg != profile.weight_kg:
        svc.record_weight(session, user.id, body.weight_kg, "manual")
    for field, value in body.model_dump().items():
        setattr(profile, field, value)
    profile.source = "manual"
    session.add(profile)
    session.commit()
    return _out(session, user.id)
