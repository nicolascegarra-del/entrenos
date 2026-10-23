"""
Análisis automático de cada entreno con la IA que tenga configurada el usuario.

- Se activa en Ajustes → Asistente IA (desactivado por defecto), por deportes y con un tope diario.
- Solo entrenos recientes (48 h) y de al menos 10 minutos: al sincronizar un histórico antiguo no se
  analiza cada actividad (coste).
- La IA recibe ya calculado lo básico (detalle del entreno, plan de los próximos días y forma) y puede
  consultar más con las mismas herramientas que el asistente. Responde en un formato fijo y corto.
- Al terminar se avisa con una notificación (desactivable) y se guarda en `activity_review`.
"""

import logging
from datetime import UTC, date, datetime, time, timedelta

from sqlmodel import Session, col, func, select

from app.core.crypto import decrypt_secret
from app.models import Activity, ActivityReview, AiProvider, AiProviderConfig, AiReviewSettings
from app.services import ai_tools, coach, notifications
from app.services.llm import PROVIDERS, LLMError, stream_chat
from app.services.plan_steps import local_day, sport_family

logger = logging.getLogger(__name__)

MIN_DURATION_S = 600
RECENT = timedelta(hours=48)

REVIEW_PROMPT = """\
Eres el entrenador personal de APP ENTRENOS. Acaba de sincronizarse un entreno y escribes su análisis.
Español de España, de tú, claro, motivador pero honesto. Máximo unas 170 palabras.

Usa los DATOS que te paso (son reales; no inventes cifras). Si te falta algo importante, consúltalo con las
herramientas (zonas, progresión, plan, salud, recorrido repetido). Si el reloj no registra un dato, no lo
menciones como si existiera.

Formato exacto, con estos títulos en negrita y 1–3 frases o viñetas cada uno:
**Cómo ha ido**: ritmo, pulso, zonas, vueltas o series; si había sesión planificada, qué tal se cumplió.
**Qué te aporta**: el tipo de estímulo (base aeróbica, umbral, VO2max, fuerza, recuperación) y cómo mueve
tu forma física y tu fatiga.
**A mejorar**: lo más relevante y concreto (p. ej. salida rápida, deriva de pulso, rodaje suave demasiado
intenso, técnica en fuerza). Si todo está bien, dilo.
**Próximos días**: qué te toca según tu plan y tu frescura, y un consejo práctico.

No es consejo médico: ante dolor o síntomas, recomienda consultar con un profesional.
"""


# ─── Ajustes y comprobaciones ────────────────────────────────────────────────


def get_settings(session: Session, user_id: int) -> AiReviewSettings:
    return session.get(AiReviewSettings, user_id) or AiReviewSettings(user_id=user_id)


def active_config(session: Session, user_id: int) -> AiProviderConfig | None:
    """La IA que usaría el asistente: la predeterminada activa o la primera activa."""
    rows = session.exec(select(AiProviderConfig).where(
        AiProviderConfig.user_id == user_id, col(AiProviderConfig.enabled)
    )).all()  # fmt: skip
    return next((c for c in rows if c.is_default), rows[0] if rows else None)


def reviews_today(session: Session, user_id: int, today: date | None = None) -> int:
    start = datetime.combine(today or datetime.now(UTC).date(), time.min, tzinfo=UTC)
    return session.exec(select(func.count(col(ActivityReview.id))).where(
        ActivityReview.user_id == user_id, ActivityReview.created_at >= start
    )).one()  # fmt: skip


def review_family(sport: str) -> str:
    family = sport_family(sport)
    return family if family in ("running", "cycling", "strength", "swimming") else "other"


def skip_reason(session: Session, activity: Activity, now: datetime | None = None) -> str | None:
    """Por qué no se analizaría automáticamente esta actividad (None = se analiza)."""
    now = now or datetime.now(UTC)
    settings = get_settings(session, activity.user_id)
    if not settings.enabled:
        return "desactivado"
    if review_family(activity.sport) not in (settings.sports or []):
        return "deporte"
    if activity.duration_s < MIN_DURATION_S:
        return "corta"
    start = activity.start_time if activity.start_time.tzinfo else activity.start_time.replace(tzinfo=UTC)
    if now - start > RECENT:
        return "antigua"
    if session.exec(select(ActivityReview.id).where(ActivityReview.activity_id == activity.id)).first():
        return "ya analizada"
    if active_config(session, activity.user_id) is None:
        return "sin IA"
    if reviews_today(session, activity.user_id) >= settings.daily_max:
        return "tope diario"
    return None


def _enqueue(review_id: int) -> None:
    from app.tasks.ai import review_activity_task

    review_activity_task.apply_async(args=[review_id], argsrepr="(análisis)")


def queue_reviews(session: Session, user_id: int, since: datetime) -> list[int]:
    """Crea y encola el análisis de las actividades nuevas (creadas desde `since`) que lo merezcan."""
    queued = []
    activities = session.exec(select(Activity).where(
        Activity.user_id == user_id, col(Activity.created_at) >= since
    ).order_by(col(Activity.start_time))).all()  # fmt: skip
    for a in activities:
        if skip_reason(session, a) is not None:
            continue
        review = ActivityReview(activity_id=a.id, user_id=user_id)
        session.add(review)
        session.commit()
        session.refresh(review)
        _enqueue(review.id)
        queued.append(review.id)
    return queued


def request_review(session: Session, activity: Activity) -> ActivityReview:
    """Análisis pedido a mano (o regenerar): vuelve a pendiente y se encola."""
    review = session.exec(select(ActivityReview).where(ActivityReview.activity_id == activity.id)).first()
    review = review or ActivityReview(activity_id=activity.id, user_id=activity.user_id)
    review.status, review.error, review.updated_at = "pending", "", datetime.now(UTC)
    session.add(review)
    session.commit()
    session.refresh(review)
    _enqueue(review.id)
    return review


# ─── Generación ──────────────────────────────────────────────────────────────


def facts(session: Session, user_id: int, activity: Activity) -> str:
    """Datos ya calculados que acompañan a la petición (detalle, plan próximo y forma)."""
    day = local_day(activity.start_time, activity.timezone)
    parts = []
    for name, args in (
        ("detalle_actividad", {"id": activity.id}),
        ("plan_y_objetivos", {"desde": day.isoformat(), "hasta": (day + timedelta(days=7)).isoformat()}),
        ("progresion", {"metrica": "forma", "dias": 14}),
    ):
        label, text = ai_tools.execute(session, user_id, name, args)
        parts.append(f"### {label}\n{text}")
    return "\n\n".join(parts)


def _summary_line(content: str) -> str:
    """Primera frase útil del análisis para la notificación."""
    for line in content.splitlines():
        text = line.replace("**Cómo ha ido**", "").replace("**", "").strip(" :-*")
        if len(text) > 20:
            return text[:140] + ("…" if len(text) > 140 else "")
    return "Ya puedes ver el análisis de tu entreno."


def generate(session: Session, review_id: int) -> ActivityReview | None:
    """Escribe el análisis con la IA del usuario y avisa cuando está listo."""
    review = session.get(ActivityReview, review_id)
    if review is None:
        return None
    activity = session.get(Activity, review.activity_id)
    config = active_config(session, review.user_id)
    if activity is None or config is None:
        review.status, review.error = "error", "Configura un asistente de IA en Ajustes."
        session.add(review)
        session.commit()
        return review
    provider = AiProvider(config.provider)
    question = (f"Analiza este entreno: «{activity.name or activity.sport}» del "
                f"{local_day(activity.start_time, activity.timezone).strftime('%d/%m/%Y')}.\n\n"
                f"DATOS:\n{facts(session, review.user_id, activity)}\n\n"
                f"{coach.context_block(session, review.user_id)}")  # fmt: skip
    parts: list[str] = []
    consulted: list[str] = []
    tokens_in = tokens_out = None
    try:
        for chunk in stream_chat(
            provider, decrypt_secret(config.key_enc), config.model, REVIEW_PROMPT,
            [{"role": "user", "content": question}], tools=ai_tools.READ_TOOLS,
            executor=lambda call: ai_tools.execute(session, review.user_id, call.name, call.args),
        ):  # fmt: skip
            if chunk.text:
                parts.append(chunk.text)
            if chunk.tool:
                consulted.append(chunk.tool)
            tokens_in = chunk.input_tokens if chunk.input_tokens is not None else tokens_in
            tokens_out = chunk.output_tokens if chunk.output_tokens is not None else tokens_out
    except LLMError as exc:
        logger.warning("Análisis de entreno: error del proveedor", extra={"status": exc.status})
        review.status, review.error = "error", exc.message[:255]
        review.updated_at = datetime.now(UTC)
        session.add(review)
        session.commit()
        return review
    content = "".join(parts).strip()
    review.status = "done" if content else "error"
    review.error = "" if content else "La IA no devolvió ningún análisis."
    review.content, review.tools = content, consulted or None
    review.provider, review.model = provider.value, config.model
    review.input_tokens, review.output_tokens = tokens_in, tokens_out
    review.updated_at = datetime.now(UTC)
    session.add(review)
    session.commit()
    if content:
        try:
            key = f"review:{review.id}:{int(review.updated_at.timestamp())}"
            title = f"Análisis de «{activity.name or 'tu entreno'}»"
            notifications.notify(session, review.user_id, "activity_review", key, title, _summary_line(content),
                                 f"/actividades/{activity.id}")  # fmt: skip
        except Exception:  # noqa: BLE001 - el aviso es secundario
            session.rollback()
    return review


def provider_label(review: ActivityReview) -> str | None:
    if not review.provider:
        return None
    return f"{PROVIDERS[AiProvider(review.provider)].label.split(' (')[0]} · {review.model}"
