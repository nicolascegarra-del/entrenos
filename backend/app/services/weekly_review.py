"""
Revisión semanal con el entrenador IA.

El domingo por la tarde (18:00 en la zona horaria de la persona) se crea la revisión de la semana y se avisa al
móvil (desactivable). La persona responde en un minuto (energía, sueño, estrés, motivación de 1 a 5, molestias y un
comentario) y la IA escribe el resumen con sus datos de la semana: qué hizo frente al plan, cómo llega y qué toca.
Puede guardar molestias en la ficha (si hay consentimiento) y proponer cambios en el plan, que la persona confirma.
También se puede hacer cuando se quiera desde el asistente.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.core.crypto import decrypt_secret
from app.models import AiProvider, CoachSettings, User, UserStatus, WeeklyCheckin
from app.services import ai_tools, coach, notifications
from app.services.activity_review import active_config
from app.services.llm import LLMError, stream_chat

logger = logging.getLogger(__name__)

SUNDAY_HOUR = 18
SCALE = ("energia", "sueno", "estres", "motivacion")

SUMMARY_PROMPT = """\
Eres su entrenador personal (cercano y directo, de tú, español de España). Es la revisión semanal.
Tienes sus respuestas de cómo se ha sentido y su ficha. Consulta con las herramientas lo que necesites de la semana
(plan_y_objetivos, buscar_actividades de lunes a hoy, progresion para forma y carga, salud_diaria).

Escribe un resumen corto con estos títulos en negrita:
**Tu semana** (qué hizo frente a lo previsto, con cifras reales),
**Cómo llegas** (cruza sus respuestas con frescura, carga reciente, sueño y FC en reposo),
**Lo que toca** (2-4 puntos concretos para la próxima semana).

- Si cuenta molestias, tenlas en cuenta; si hay consentimiento de salud, guárdalas en su ficha con fecha. Si el dolor
  persiste, es agudo o va a más, recomienda fisio o médico y no des tratamientos.
- Si conviene cambiar alguna sesión de los próximos días (descansar, aflojar, mover), propónlo con
  proponer_cambio_plan (lo confirma la persona; no digas que ya está cambiado).
- No inventes cifras. Si no hay datos de algo, dilo.
"""


def _tz(session: Session, user_id: int) -> ZoneInfo:
    from app.services.notifications import get_prefs

    try:
        return ZoneInfo(get_prefs(session, user_id).timezone)
    except Exception:  # noqa: BLE001
        return ZoneInfo("Europe/Madrid")


def current(session: Session, user_id: int) -> WeeklyCheckin | None:
    return session.exec(
        select(WeeklyCheckin).where(WeeklyCheckin.user_id == user_id).order_by(WeeklyCheckin.week_start.desc())  # type: ignore[attr-defined]
    ).first()


def open_week(session: Session, user_id: int, today: date | None = None, notify: bool = False) -> WeeklyCheckin:
    """La revisión de esta semana (la crea si no existe) y, si se pide, avisa al móvil."""
    today = today or datetime.now(_tz(session, user_id)).date()
    week = coach.checkin_week(today)
    row = session.exec(
        select(WeeklyCheckin).where(WeeklyCheckin.user_id == user_id, WeeklyCheckin.week_start == week)
    ).first()
    if row is None:
        row = WeeklyCheckin(user_id=user_id, week_start=week)
        session.add(row)
        session.commit()
        session.refresh(row)
        if notify:
            try:
                notifications.notify(session, user_id, "weekly_review", f"checkin:{row.id}", "¿Qué tal la semana?",
                                     "Cuéntame en un minuto cómo te has sentido y te digo qué toca la próxima.",
                                     "/asistente/semana")  # fmt: skip
            except Exception:  # noqa: BLE001 - el aviso es secundario
                session.rollback()
    return row


def due_tick(session: Session, now: datetime | None = None) -> int:
    """Cada hora: el domingo desde las 18:00 locales, abre la revisión de quien tenga IA y la revisión activa."""
    from app.models import AiProviderConfig

    now = now or datetime.now(UTC)
    users = session.exec(
        select(User.id)
        .join(AiProviderConfig, AiProviderConfig.user_id == User.id)
        .where(User.status == UserStatus.ACTIVE, AiProviderConfig.enabled)
        .distinct()
    ).all()
    opened = 0
    for uid in users:
        s = session.get(CoachSettings, uid)
        if s is not None and not s.weekly_review:
            continue
        local = now.astimezone(_tz(session, uid))
        if local.weekday() != 6 or local.hour < SUNDAY_HOUR:
            continue
        week = coach.checkin_week(local.date())
        exists = session.exec(
            select(WeeklyCheckin.id).where(WeeklyCheckin.user_id == uid, WeeklyCheckin.week_start == week)
        ).first()
        if exists is None:
            open_week(session, uid, local.date(), notify=True)
            opened += 1
    return opened


def clean_answers(raw: dict) -> dict:
    """Respuestas válidas: escalas 1-5 y textos cortos."""
    out: dict = {}
    for k in SCALE:
        v = raw.get(k)
        if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 5:
            out[k] = v
    for k in ("molestias", "comentario"):
        if isinstance(raw.get(k), str) and raw[k].strip():
            out[k] = " ".join(raw[k].split())[:500]
    if not out:
        raise coach.CoachError("Responde al menos a una pregunta.")
    return out


def generate(session: Session, checkin_id: int) -> WeeklyCheckin | None:
    """Resumen del entrenador con sus respuestas y los datos de la semana."""
    row = session.get(WeeklyCheckin, checkin_id)
    if row is None:
        return None
    config = active_config(session, row.user_id)
    if config is None:
        row.status, row.error = "error", "Configura un asistente de IA en Ajustes."
        session.add(row)
        session.commit()
        return row
    system = SUMMARY_PROMPT + "\n" + coach.context_block(session, row.user_id)
    question = (
        f"Revisión de la semana del {row.week_start.strftime('%d/%m/%Y')} (hoy es "
        f"{date.today().strftime('%d/%m/%Y')}). Sus respuestas: {coach.answers_text(row.answers)}."
    )
    parts: list[str] = []
    effects: list[dict] = []

    def run(call) -> tuple[str, str]:
        label, result = ai_tools.execute(session, row.user_id, call.name, call.args)
        if (effect := ai_tools.effect_of(call.name, result)) is not None:
            effects.append(effect)
        return label, result

    try:
        history = [{"role": "user", "content": question}]
        key = decrypt_secret(config.key_enc)
        for chunk in stream_chat(AiProvider(config.provider), key, config.model, system, history,
                                 tools=ai_tools.TOOLS, executor=run):  # fmt: skip
            if chunk.text:
                parts.append(chunk.text)
    except LLMError as exc:
        row.status, row.error = "error", exc.message[:255]
        row.updated_at = datetime.now(UTC)
        session.add(row)
        session.commit()
        return row
    session.refresh(row)
    content = "".join(parts).strip()
    row.summary = content
    row.status = "done" if content else "error"
    row.error = "" if content else "La IA no devolvió ningún resumen."
    row.effects = effects or None
    row.updated_at = datetime.now(UTC)
    session.add(row)
    session.commit()
    return row


def next_week_start(today: date) -> date:
    return coach.checkin_week(today) + timedelta(days=7)
