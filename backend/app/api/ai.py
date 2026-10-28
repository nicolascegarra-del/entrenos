"""
Asistente IA: cuentas de cada usuario (ChatGPT, Gemini, Claude) con su propia clave de API
y chat sobre sus entrenamientos con respuesta en streaming (SSE).

Las claves se guardan cifradas y nunca vuelven al cliente; las preguntas y respuestas
no se registran en los logs.
"""

import json
import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, col, func, select

from app.api.deps import CurrentUser, SessionDep, require_module
from app.api.goals import list_goals
from app.api.progress import summary
from app.core.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.db import engine
from app.core.rate_limit import limiter
from app.models import Activity, AiProvider, AiProviderConfig, ChatConversation, ChatMessage, User
from app.services import ai_tools, chat_markers, coach
from app.services import progress as prog
from app.services.ai_context import conversation_title, format_context, interview_prompt, system_prompt
from app.services.ai_tools import clock
from app.services.insights import build_insights
from app.services.llm import PROVIDERS, LLMError, check_model, list_models, stream_chat
from app.services.plan_steps import local_day
from app.services.profile import age_on, get_profile
from app.services.zones import latest_zones

logger = logging.getLogger(__name__)
router = APIRouter(tags=["asistente IA"], dependencies=[Depends(require_module("ia"))])

MODEL_PATTERN = r"^[A-Za-z0-9._:/-]{1,100}$"
HISTORY_MESSAGES = 20  # turnos previos que se reenvían al modelo
_NOT_FOUND = {404: {"description": "No encontrado"}}


# ─── Esquemas ────────────────────────────────────────────────────────────────


class ProviderOut(BaseModel):
    provider: AiProvider
    label: str
    keys_url: str
    privacy: str
    default_model: str
    suggested_models: list[str]
    configured: bool
    model: str | None
    key_last4: str | None
    enabled: bool
    is_default: bool
    updated_at: datetime | None


class ProvidersOut(BaseModel):
    providers: list[ProviderOut]
    daily_limit: int
    used_today: int


class ProviderIn(BaseModel):
    api_key: str | None = Field(default=None, min_length=8, max_length=300, description="Vacía = conservar la actual")
    model: str = Field(pattern=MODEL_PATTERN)
    enabled: bool = True
    is_default: bool = False


class ModelsIn(BaseModel):
    api_key: str | None = Field(default=None, min_length=8, max_length=300, description="Vacía = usar la guardada")


class ModelsOut(BaseModel):
    models: list[str]
    recommended: list[str]


class TestOut(BaseModel):
    ok: bool
    model: str
    models: list[str]


class ChatIn(BaseModel):
    message: str = Field(default="", max_length=2000)
    conversation_id: int | None = None
    provider: AiProvider | None = None
    mode: Literal["interview"] | None = Field(default=None, description="interview = entrevista inicial")
    regenerate: bool = Field(
        default=False,
        description="Repetir la respuesta a la última pregunta de la conversación (Reintentar / Otra respuesta)",
    )


class FeedbackIn(BaseModel):
    value: Literal[-1, 0, 1]


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    provider: str | None
    model: str | None
    tools: list[str] | None = None
    effects: list[dict] | None = None  # ficha, propuestas del plan, botones (opciones/sugerencias), incompleta
    feedback: int | None = None
    created_at: datetime


class ConversationBrief(BaseModel):
    id: int
    title: str
    updated_at: datetime


class ConversationOut(ConversationBrief):
    messages: list[MessageOut]


# ─── Utilidades ──────────────────────────────────────────────────────────────


def _configs(session: Session, user_id: int) -> dict[AiProvider, AiProviderConfig]:
    rows = session.exec(select(AiProviderConfig).where(AiProviderConfig.user_id == user_id)).all()
    return {AiProvider(c.provider): c for c in rows}


def _used_today(session: Session, user_id: int) -> int:
    start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    return session.exec(
        select(func.count(col(ChatMessage.id)))
        .join(ChatConversation, col(ChatConversation.id) == col(ChatMessage.conversation_id))
        .where(ChatConversation.user_id == user_id, ChatMessage.role == "user", ChatMessage.created_at >= start)
    ).one()


def _owned_conversation(session: Session, user_id: int, conversation_id: int) -> ChatConversation:
    conversation = session.get(ChatConversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada.")
    return conversation


def _pick_config(configs: dict[AiProvider, AiProviderConfig], wanted: AiProvider | None) -> AiProviderConfig:
    """Proveedor pedido, o el predeterminado, o el primero activo."""
    active = {p: c for p, c in configs.items() if c.enabled}
    if wanted is not None:
        if wanted not in active:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{PROVIDERS[wanted].label} no está configurado o activo.")
        return active[wanted]
    if not active:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Configura un asistente de IA en Ajustes para poder hacer preguntas."
        )
    return next((c for c in active.values() if c.is_default), next(iter(active.values())))


def _gather(session: Session, user: User) -> dict:
    """Datos del usuario para el contexto del asistente (sin email ni nombre)."""
    profile = get_profile(session, user.id)
    today = date.today()
    activities = session.exec(
        select(Activity).where(Activity.user_id == user.id).order_by(col(Activity.start_time).desc()).limit(20)
    ).all()
    all_activities = prog.user_activities(session, user.id)
    _, loads = prog.loads_by_day(
        all_activities, prog.user_thresholds(session, user.id), prog.user_rpes(session, user.id)
    )
    weeks = prog.weekly_volume(
        all_activities, loads, prog.week_start(today) - timedelta(weeks=7), prog.week_start(today)
    )
    current = latest_zones(session, user.id)
    zones = {}
    if current:
        thr = current.thresholds
        zones = {
            "lthr": thr.get("lthr"),
            "lthr_source": thr.get("lthr_source"),
            "pace_source": thr.get("pace_source"),
            "threshold_pace": clock(thr.get("threshold_pace_s_km")),
            "hr": [
                f"{z['name']} {z['min']}–{z['max'] if z['max'] is not None else '…'}"
                for z in current.zones.get("hr", [])
            ],
        }
    from app.services.health_views import active_rest_period

    rest = active_rest_period(session, user.id, today)
    return {
        "rest_mode": {
            "start_date": rest.start_date.isoformat(),
            "end_date": rest.end_date.isoformat() if rest.end_date else None,
        }
        if rest
        else None,  # fmt: skip
        "profile": {
            "age": age_on(profile.birth_date, today) if profile.birth_date else None,
            "sex": profile.sex,
            "weight_kg": profile.weight_kg,
            "height_cm": profile.height_cm,
        },
        "summary": summary(session, user).model_dump(mode="json"),
        "insights": build_insights(session, user.id, 90),
        "zones": zones,
        "weeks": [w | {"week": str(w["week"])} for w in weeks],
        "activities": [
            {
                "id": a.id,
                "is_race": a.is_race,
                "day": local_day(a.start_time, a.timezone).isoformat(),
                "sport": a.sport,
                "name": a.name,
                "distance_m": a.distance_m,
                "duration_s": a.duration_s,
                "avg_hr": a.avg_hr,
            }
            for a in activities
        ],
        "goals": [g.model_dump(mode="json") for g in list_goals(session, user) if g.days_left >= -30],
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ─── Cuentas de IA ───────────────────────────────────────────────────────────


@router.get("/ai/providers", summary="Asistentes de IA disponibles y configurados")
def get_providers(session: SessionDep, user: CurrentUser) -> ProvidersOut:
    configs = _configs(session, user.id)
    providers = []
    for provider, info in PROVIDERS.items():
        c = configs.get(provider)
        providers.append(
            ProviderOut(
                provider=provider,
                label=info.label,
                keys_url=info.keys_url,
                privacy=info.privacy,
                default_model=info.default_model,
                suggested_models=list(info.suggested_models),
                configured=c is not None,
                model=c.model if c else None,
                key_last4=c.key_last4 if c else None,
                enabled=c.enabled if c else False,
                is_default=c.is_default if c else False,
                updated_at=c.updated_at if c else None,
            )
        )
    return ProvidersOut(
        providers=providers, daily_limit=get_settings().chat_daily_limit, used_today=_used_today(session, user.id)
    )


@router.put(
    "/ai/providers/{provider}",
    summary="Guardar la cuenta de un asistente",
    description=(
        "La clave se cifra al guardarla y no se devuelve nunca. Sin `api_key` se conserva la actual. Si cambian la "
        "clave o el modelo, se comprueba antes que el modelo responde."
    ),
    responses={400: {"description": "La clave o el modelo no funcionan (mensaje con el motivo)"}},
)
def save_provider(provider: AiProvider, body: ProviderIn, session: SessionDep, user: CurrentUser) -> ProvidersOut:
    configs = _configs(session, user.id)
    config = configs.get(provider)
    api_key = body.api_key.strip() if body.api_key else None
    if config is None:
        if not api_key:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Introduce la clave de API.")
        config = AiProviderConfig(user_id=user.id, provider=provider, model=body.model, key_enc="", key_last4="")
    # Si cambia la clave o el modelo, se comprueba que el modelo responde antes de guardar: los proveedores
    # siguen listando modelos retirados y así nunca queda guardado uno que falle.
    if body.enabled and (api_key or body.model != config.model):
        try:
            check_model(provider, api_key or decrypt_secret(config.key_enc), body.model)
        except LLMError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from exc
    if api_key:
        config.key_enc, config.key_last4 = encrypt_secret(api_key), api_key[-4:]
    config.model, config.enabled = body.model, body.enabled
    # El primero que se configura queda como predeterminado; marcar uno desmarca los demás.
    others_default = any(c.is_default and c.enabled for p, c in configs.items() if p != provider)
    config.is_default = body.enabled and (body.is_default or not others_default)
    if config.is_default:
        for p, c in configs.items():
            if p != provider and c.is_default:
                c.is_default = False
                session.add(c)
    session.add(config)
    session.commit()
    return get_providers(session, user)


@router.delete("/ai/providers/{provider}", summary="Quitar la cuenta de un asistente", status_code=204)
def delete_provider(provider: AiProvider, session: SessionDep, user: CurrentUser) -> Response:
    configs = _configs(session, user.id)
    config = configs.pop(provider, None)
    if config is not None:
        was_default = config.is_default
        session.delete(config)
        if was_default:
            replacement = next((c for c in configs.values() if c.enabled), None)
            if replacement:
                replacement.is_default = True
                session.add(replacement)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/ai/providers/{provider}/models",
    summary="Modelos de chat disponibles en la cuenta",
    description="Con la clave del cuerpo (al configurar) o la guardada. Los recomendados van primero.",
    responses={400: {"description": "La clave no funciona"}},
)
@limiter.limit("20/minute")
def provider_models(
    request: Request, provider: AiProvider, body: ModelsIn, session: SessionDep, user: CurrentUser
) -> ModelsOut:
    config = _configs(session, user.id).get(provider)
    api_key = body.api_key.strip() if body.api_key else None
    if api_key is None:
        if config is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Introduce la clave de API.")
        api_key = decrypt_secret(config.key_enc)
    try:
        models = list_models(provider, api_key)
    except LLMError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from exc
    recommended = [m for m in PROVIDERS[provider].suggested_models if m in models]
    return ModelsOut(models=[m for m in models if m not in recommended], recommended=recommended)


@router.post(
    "/ai/providers/{provider}/test",
    summary="Probar la clave y el modelo guardados",
    description=(
        "Pide la lista de modelos (comprueba la clave) y una respuesta mínima al modelo elegido (comprueba que "
        "sigue disponible: los proveedores listan modelos retirados)."
    ),
    responses={400: {"description": "La clave o el modelo no funcionan (mensaje con el motivo)"}},
)
@limiter.limit("10/minute")
def test_provider(request: Request, provider: AiProvider, session: SessionDep, user: CurrentUser) -> TestOut:
    config = _configs(session, user.id).get(provider)
    if config is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guarda primero la clave de este asistente.")
    api_key = decrypt_secret(config.key_enc)
    try:
        models = list_models(provider, api_key)
        check_model(provider, api_key, config.model)
    except LLMError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from exc
    return TestOut(ok=True, model=config.model, models=models)


# ─── Conversaciones ──────────────────────────────────────────────────────────


@router.get("/chat/conversations", summary="Conversaciones (más recientes primero)")
def list_conversations(
    session: SessionDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ConversationBrief]:
    rows = session.exec(
        select(ChatConversation)
        .where(ChatConversation.user_id == user.id)
        .order_by(col(ChatConversation.updated_at).desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [ConversationBrief.model_validate(c, from_attributes=True) for c in rows]


@router.get("/chat/conversations/{conversation_id}", summary="Mensajes de una conversación", responses=_NOT_FOUND)
def get_conversation(conversation_id: int, session: SessionDep, user: CurrentUser) -> ConversationOut:
    conversation = _owned_conversation(session, user.id, conversation_id)
    messages = session.exec(
        select(ChatMessage).where(ChatMessage.conversation_id == conversation_id).order_by(col(ChatMessage.id))
    ).all()
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        updated_at=conversation.updated_at,
        messages=[MessageOut.model_validate(m, from_attributes=True) for m in messages],
    )


@router.delete(
    "/chat/conversations/{conversation_id}", summary="Borrar una conversación", status_code=204, responses=_NOT_FOUND
)
def delete_conversation(conversation_id: int, session: SessionDep, user: CurrentUser) -> Response:
    session.delete(_owned_conversation(session, user.id, conversation_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/chat/messages/{message_id}/feedback",
    summary="Valorar una respuesta del asistente (útil / no útil)",
    responses={404: {"description": "El mensaje no existe o no es tuyo."}},
)
def message_feedback(message_id: int, body: FeedbackIn, session: SessionDep, user: CurrentUser) -> dict:
    row = session.get(ChatMessage, message_id)
    if row is None or row.role != "assistant":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mensaje no encontrado.")
    _owned_conversation(session, user.id, row.conversation_id)
    row.feedback = body.value or None
    session.add(row)
    session.commit()
    return {"feedback": row.feedback}


@router.post(
    "/chat",
    summary="Preguntar al asistente (respuesta en streaming)",
    description=(
        "Devuelve `text/event-stream` con los eventos `meta` ({conversation_id, provider, model}), `delta` "
        "({text}) varias veces, y `done` ({message_id}) o `error` ({message}). La pregunta se guarda antes de "
        "llamar al proveedor; la respuesta, al terminar."
    ),
    responses={
        409: {"description": "No hay ningún asistente configurado y activo"},
        429: {"description": "Límite diario de mensajes alcanzado"},
        **_NOT_FOUND,
    },
)
@limiter.limit("15/minute")
def chat(request: Request, body: ChatIn, session: SessionDep, user: CurrentUser) -> StreamingResponse:
    config = _pick_config(_configs(session, user.id), body.provider)
    limit = get_settings().chat_daily_limit
    if _used_today(session, user.id) >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, f"Has llegado al límite de {limit} preguntas por hoy. Vuelve mañana."
        )

    message = body.message.strip()
    if body.regenerate:
        # Reintentar u «Otra respuesta»: se repite la última pregunta y se quita la respuesta que hubiera después.
        if body.conversation_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Falta la conversación.")
        conversation = _owned_conversation(session, user.id, body.conversation_id)
        last_user = session.exec(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.id, ChatMessage.role == "user")
            .order_by(col(ChatMessage.id).desc())
        ).first()
        if last_user is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No hay ninguna pregunta que repetir.")
        for old in session.exec(
            select(ChatMessage).where(ChatMessage.conversation_id == conversation.id, ChatMessage.id > last_user.id)
        ).all():
            session.delete(old)
        session.flush()
    elif not message:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Escribe tu pregunta.")
    elif body.conversation_id is not None:
        conversation = _owned_conversation(session, user.id, body.conversation_id)
    else:
        conversation = ChatConversation(user_id=user.id, title=conversation_title(message))
        session.add(conversation)
        session.flush()
    previous = session.exec(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation.id)
        .order_by(col(ChatMessage.id).desc())
        .limit(HISTORY_MESSAGES)
    ).all()
    history = [{"role": m.role, "content": m.content} for m in reversed(previous)]
    if not body.regenerate:
        history.append({"role": "user", "content": message})
        session.add(ChatMessage(conversation_id=conversation.id, role="user", content=message))
    conversation.updated_at = datetime.now(UTC)
    session.add(conversation)
    session.commit()

    # Todo lo que necesita la BD se lee aquí: el generador corre después y usa su propia sesión.
    system = system_prompt(format_context(_gather(session, user), date.today()))
    system += "\n\n" + coach.context_block(session, user.id)
    if body.mode == "interview":
        system += "\n" + interview_prompt()
    # Calcular el contexto guarda cachés (curva de ritmos, huellas de recorrido) en las actividades: se
    # confirman ya para no dejar filas bloqueadas mientras dura la respuesta (las herramientas escriben las mismas).
    session.commit()
    provider, model, conversation_id, user_id = AiProvider(config.provider), config.model, conversation.id, user.id
    api_key = decrypt_secret(config.key_enc)

    consulted_box: list[str] = []

    def events() -> Iterator[str]:
        yield _sse("meta", {"conversation_id": conversation_id, "provider": provider, "model": model})
        parts: list[str] = []
        consulted = consulted_box
        effects: list[dict] = []
        pending: list[dict] = []
        tokens_in = tokens_out = None
        # Las herramientas leen la BD con su propia sesión (el generador corre después de la petición).
        with Session(engine) as tools_db:

            def run_tool(call) -> tuple[str, str]:
                label, result = ai_tools.execute(tools_db, user_id, call.name, call.args)
                if (effect := ai_tools.effect_of(call.name, result)) is not None:
                    effects.append(effect)
                    pending.append(effect)
                return label, result

            try:
                for chunk in stream_chat(provider, api_key, model, system, history, tools=ai_tools.TOOLS,
                                         executor=run_tool):  # fmt: skip
                    if chunk.tool:
                        consulted.append(chunk.tool)
                        yield _sse("tool", {"label": chunk.tool})
                    while pending:
                        yield _sse("effect", pending.pop(0))
                    if chunk.text:
                        parts.append(chunk.text)
                        yield _sse("delta", {"text": chunk.text})
                    tokens_in = chunk.input_tokens if chunk.input_tokens is not None else tokens_in
                    tokens_out = chunk.output_tokens if chunk.output_tokens is not None else tokens_out
            except LLMError as exc:
                logger.warning("Error del proveedor de IA", extra={"user_id": user_id, "status": exc.status})
                # Lo que ya había escrito no se pierde: se guarda como respuesta incompleta (con «Continuar»).
                partial = chat_markers.parse("".join(parts))[0]
                saved = _save_answer(partial, [*effects, {"tipo": "incompleta"}]) if partial else None
                yield _sse("error", {"message": exc.message, "partial_id": saved})
                return
        answer, buttons = chat_markers.parse("".join(parts))
        if not answer:
            yield _sse("error", {"message": "El entrenador no ha podido responder esta vez. Prueba a reintentarlo."})
            return
        yield _sse("done", {"message_id": _save_answer(answer, [*effects, *buttons], tokens_in, tokens_out)})

    def _save_answer(content: str, extra: list[dict], tokens_in: int | None = None,
                     tokens_out: int | None = None) -> int:  # fmt: skip
        with Session(engine) as db:
            row = ChatMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=content,
                provider=provider,
                model=model,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                tools=consulted_box or None,
                effects=extra or None,
            )
            db.add(row)
            db.commit()
            return row.id

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
