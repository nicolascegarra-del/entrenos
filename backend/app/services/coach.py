"""
Entrenador personal con IA: memoria del atleta, herramientas para que la IA guarde lo que le cuentas y
proponga cambios en el plan, entrevista inicial y revisión semanal.

- **Memoria** (`CoachMemory`): datos que el reloj no sabe (historial, lesiones, salud, disponibilidad,
  preferencias, objetivos, vida). Los guarda la IA cuando se los cuentas, o tú en Ajustes. Van siempre en
  el contexto de la IA. Lesiones y salud solo con consentimiento explícito (`CoachSettings`).
- **Herramientas de escritura** para el modelo: guardar / corregir / olvidar un dato, completar el perfil
  (nacimiento, sexo, peso, altura) y los umbrales conocidos (FC máx., FC y ritmo umbral, VO2max), terminar la
  entrevista y proponer un cambio de una sesión del plan. Nada cambia el plan sin tu confirmación.
- **Efectos**: lo que hace cada herramienta se devuelve también al chat (`efecto`) para enseñarlo con
  «Deshacer» o «Aceptar / Rechazar».
"""

from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, col, select

from app.models import CoachMemory, CoachSettings, PlannedSession, PlanProposal, WeeklyCheckin

CATEGORIES = {
    "historial": "Historial deportivo",
    "lesiones": "Lesiones y molestias",
    "salud": "Salud y medicación",
    "disponibilidad": "Disponibilidad y lugares",
    "preferencias": "Preferencias",
    "objetivos": "Objetivos a largo plazo",
    "vida": "Trabajo, sueño y vida diaria",
    "otros": "Otros",
}
HEALTH = ("lesiones", "salud")
MAX_MEMORIES = 150
CONTEXT_CHARS = 3500
CHECKIN_CONTEXT_DAYS = 10


class CoachError(ValueError):
    """Petición no válida (para la IA o para la API)."""


def settings(session: Session, user_id: int) -> CoachSettings:
    return session.get(CoachSettings, user_id) or CoachSettings(user_id=user_id)


def memories(session: Session, user_id: int) -> list[CoachMemory]:
    return list(
        session.exec(
            select(CoachMemory)
            .where(CoachMemory.user_id == user_id)
            .order_by(col(CoachMemory.category), col(CoachMemory.created_at))
        ).all()
    )


def save_memory(
    session: Session, user_id: int, category: str, content: str, source: str = "ia", replaces: int | None = None
) -> CoachMemory:
    """
    Guarda (o corrige, con `replaces`) un dato del atleta.

    Raises:
        CoachError: categoría desconocida, texto vacío, salud sin consentimiento o demasiados datos.
    """
    category = (category or "").strip().lower()
    content = " ".join((content or "").split())[:500]
    if category not in CATEGORIES:
        raise CoachError(f"Categoría desconocida: usa una de {', '.join(CATEGORIES)}.")
    if not content:
        raise CoachError("El dato está vacío.")
    if category in HEALTH and not settings(session, user_id).health_consent:
        raise CoachError(
            "Sin consentimiento para guardar datos de salud o lesiones. No lo guardes: dile que puede activarlo "
            "en Ajustes → Asistente IA → «Lo que sé de ti» si quiere que lo recuerdes."
        )
    if replaces is not None:
        row = session.get(CoachMemory, replaces)
        if row is None or row.user_id != user_id:
            raise CoachError("No existe ese dato para corregirlo.")
        row.category, row.content, row.updated_at = category, content, datetime.now(UTC)
    else:
        count = len(session.exec(select(CoachMemory.id).where(CoachMemory.user_id == user_id)).all())
        if count >= MAX_MEMORIES:
            raise CoachError("La ficha está llena: corrige (reemplaza_id) o borra datos antiguos.")
        row = CoachMemory(user_id=user_id, category=category, content=content, source=source)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def forget(session: Session, user_id: int, memory_id: int) -> CoachMemory:
    row = session.get(CoachMemory, memory_id)
    if row is None or row.user_id != user_id:
        raise CoachError("No existe ese dato.")
    session.delete(row)
    session.commit()
    return row


def set_consent(session: Session, user_id: int, consent: bool) -> CoachSettings:
    """Sin consentimiento se borran los datos de salud y lesiones que hubiera."""
    row = settings(session, user_id)
    row.health_consent = consent
    row.health_consent_at = datetime.now(UTC) if consent else None
    session.add(row)
    if not consent:
        for m in session.exec(
            select(CoachMemory).where(CoachMemory.user_id == user_id, col(CoachMemory.category).in_(HEALTH))
        ).all():
            session.delete(m)
    session.commit()
    return row


# ─── Contexto para la IA ─────────────────────────────────────────────────────


def context_block(session: Session, user_id: int, today: date | None = None) -> str:
    """«Lo que sé del atleta»: ficha, última revisión semanal y propuestas pendientes."""
    today = today or date.today()
    s = settings(session, user_id)
    lines = ["LO QUE SÉ DEL ATLETA (su ficha; úsala siempre):"]
    rows = memories(session, user_id)
    if rows:
        by_cat: dict[str, list[CoachMemory]] = {}
        for m in rows:
            by_cat.setdefault(m.category, []).append(m)
        for cat, items in by_cat.items():
            lines.append(f"- {CATEGORIES.get(cat, cat)}:")
            lines += [f"  · [{m.id}] {m.content} ({m.created_at.strftime('%d/%m/%Y')})" for m in items]
    else:
        lines.append("- (vacía: aún no sabes nada de su historial, lesiones ni disponibilidad)")
    lines.append(
        f"- Consentimiento para datos de salud y lesiones: {'sí' if s.health_consent else 'no'}."
        f" Entrevista inicial: {'hecha' if s.interview_done_at else 'pendiente'}."
    )
    checkin = session.exec(
        select(WeeklyCheckin)
        .where(WeeklyCheckin.user_id == user_id, WeeklyCheckin.status == "done")
        .order_by(col(WeeklyCheckin.week_start).desc())
    ).first()
    if checkin and (today - checkin.week_start).days <= CHECKIN_CONTEXT_DAYS + 7:
        lines.append(f"- Última revisión semanal (semana del {checkin.week_start.strftime('%d/%m')}): "
                     f"{answers_text(checkin.answers)}")  # fmt: skip
    pending = session.exec(
        select(PlanProposal).where(PlanProposal.user_id == user_id, PlanProposal.status == "pending")
    ).all()
    if pending:
        lines.append(f"- Propuestas de cambio del plan pendientes de su respuesta: {len(pending)}.")
    text = "\n".join(lines)
    return (
        text
        if len(text) <= CONTEXT_CHARS
        else text[:CONTEXT_CHARS] + "\n  … (ficha recortada: consulta memoria_del_atleta)"
    )


ANSWER_LABELS = {"energia": "energía", "sueno": "sueño", "estres": "estrés", "motivacion": "motivación"}


def answers_text(answers: dict) -> str:
    parts = [f"{label} {answers[k]}/5" for k, label in ANSWER_LABELS.items() if answers.get(k)]
    if answers.get("molestias"):
        parts.append(f"molestias: {answers['molestias']}")
    if answers.get("comentario"):
        parts.append(f"comentario: {answers['comentario']}")
    return "; ".join(parts) or "sin respuestas"


# ─── Propuestas de cambio del plan ───────────────────────────────────────────


def propose(session: Session, user_id: int, args: dict, today: date | None = None) -> PlanProposal:
    """
    Propuesta de cambio de una sesión futura (día, título, notas o bloques).

    Raises:
        CoachError: sesión ajena, pasada o ya hecha, o sin cambios válidos.
    """
    from pydantic import ValidationError

    from app.schemas.plan import BlockIn

    today = today or date.today()
    planned = session.get(PlannedSession, args.get("sesion_id"))
    if planned is None or planned.user_id != user_id:
        raise CoachError("No existe esa sesión del plan.")
    if planned.day < today or planned.activity_id is not None:
        raise CoachError("Solo se pueden cambiar sesiones de hoy en adelante que aún no estén hechas.")
    change: dict = {}
    if args.get("nuevo_dia"):
        try:
            day = date.fromisoformat(str(args["nuevo_dia"]))
        except ValueError as exc:
            raise CoachError("nuevo_dia debe ser AAAA-MM-DD.") from exc
        if day < today:
            raise CoachError("No se puede mover al pasado.")
        if day != planned.day:
            change["day"] = day.isoformat()
    if args.get("nuevo_titulo"):
        change["title"] = str(args["nuevo_titulo"])[:255]
    if args.get("notas"):
        change["notes"] = str(args["notas"])[:2000]
    if args.get("bloques"):
        try:
            change["blocks"] = [BlockIn.model_validate(b).model_dump() for b in args["bloques"]][:30]
        except (ValidationError, TypeError) as exc:
            raise CoachError(f"Bloques no válidos: {exc}"[:300]) from exc
    reason = " ".join(str(args.get("motivo") or "").split())[:500]
    if not change:
        raise CoachError("La propuesta no cambia nada.")
    if not reason:
        raise CoachError("Explica el motivo del cambio (motivo).")
    # Una propuesta pendiente por sesión: la nueva sustituye a la anterior.
    for old in session.exec(
        select(PlanProposal).where(PlanProposal.planned_session_id == planned.id, PlanProposal.status == "pending")
    ).all():
        old.status, old.decided_at = "expired", datetime.now(UTC)
        session.add(old)
    row = PlanProposal(user_id=user_id, planned_session_id=planned.id, change=change, reason=reason)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def describe(proposal: PlanProposal, planned: PlannedSession | None) -> str:
    """Resumen corto de una propuesta («Series 6×1000: del jue 30/10 al vie 31/10»)."""
    title = planned.title if planned else "Sesión"
    parts = []
    c = proposal.change
    if c.get("day") and planned:
        parts.append(f"del {planned.day.strftime('%d/%m')} al {date.fromisoformat(c['day']).strftime('%d/%m')}")
    if c.get("title"):
        parts.append(f"pasa a «{c['title']}»")
    if c.get("blocks"):
        parts.append("con bloques nuevos")
    if c.get("notes") and not parts:
        parts.append("con notas nuevas")
    return f"{title}: {', '.join(parts)}"


def decide(session: Session, user_id: int, proposal_id: int, accept: bool) -> PlanProposal:
    """Acepta (aplica a la sesión y la reenvía al reloj si toca) o rechaza una propuesta."""
    from app.models import PlannedBlock
    from app.services.plan_service import refresh_match

    row = session.get(PlanProposal, proposal_id)
    if row is None or row.user_id != user_id:
        raise CoachError("Propuesta no encontrada.")
    if row.status != "pending":
        raise CoachError("Esta propuesta ya no está pendiente.")
    planned = session.get(PlannedSession, row.planned_session_id)
    if accept and planned is not None:
        c = row.change
        if c.get("day"):
            planned.day = date.fromisoformat(c["day"])
        if c.get("title"):
            planned.title = c["title"]
        if c.get("notes"):
            planned.notes = c["notes"]
        if c.get("blocks") is not None:
            for b in session.exec(select(PlannedBlock).where(PlannedBlock.session_id == planned.id)).all():
                session.delete(b)
            session.flush()
            for position, b in enumerate(c["blocks"]):
                session.add(PlannedBlock(session_id=planned.id, position=position, **b))
        session.add(planned)
        session.flush()
        refresh_match(session, planned)
    row.status = "accepted" if accept else "rejected"
    row.decided_at = datetime.now(UTC)
    session.add(row)
    session.commit()
    if accept:
        from app.api.workouts import queue_send

        queue_send(session, user_id)  # si envía solo al reloj, se actualiza allí
    return row


# ─── Herramientas para la IA ─────────────────────────────────────────────────


def _memory_effect(action: str, m: CoachMemory) -> dict:
    return {"tipo": "memoria", "accion": action, "id": m.id, "categoria": m.category,
            "categoria_nombre": CATEGORIES.get(m.category, m.category), "dato": m.content}  # fmt: skip


def _dato(valor: object, origen: str | None, detalle: str | None = None) -> dict:
    return {"valor": valor, "origen": origen, "detalle": detalle}


def athlete_basics(session: Session, user_id: int) -> dict:
    """
    Datos con los que la app calcula (edad → FC máx. y percentiles; sexo → percentiles; peso → calorías;
    altura → IMC y zancada; FC máx. y umbral → zonas y carga), de dónde sale cada uno y cuáles faltan.

    Origen: `garmin` (perfil importado del reloj), `manual` (lo metió la persona o la entrevista),
    `actividades` (visto en sus entrenos), `reloj` (métrica que da el reloj), `test` (test confirmado) o
    `edad` / `estimada` (calculado sin datos reales: cuenta como «falta»). Con esto la entrevista enseña lo
    detectado para que lo confirme y solo pregunta lo que no hay.
    """
    from app.models import DailyMetric, SyncRun, SyncStatus
    from app.services import progress as prog
    from app.services.profile import get_profile
    from app.services.test_results import active_test, tested_hr_max

    profile = get_profile(session, user_id)
    activities = prog.user_activities(session, user_id)
    thr = prog.user_thresholds(session, user_id)
    source = profile.source if profile.source in ("garmin", "manual") else "manual"

    def field(value: object) -> dict:
        return _dato(value, source if value is not None else None)

    sex = getattr(profile.sex, "value", profile.sex)  # Sex o str según venga de la BD
    datos = {
        "fecha_nacimiento": field(profile.birth_date.isoformat() if profile.birth_date else None),
        "sexo": field(sex),
        "peso_kg": field(profile.weight_kg),
        "altura_cm": field(profile.height_cm),
    }

    top = max((a for a in activities if a.max_hr), key=lambda a: a.max_hr, default=None)
    tested = tested_hr_max(session, user_id)
    if tested and (not top or tested >= top.max_hr):
        datos["fc_max"] = _dato(tested, "test")
    elif top:
        when = top.start_time.date().strftime("%d/%m/%Y")
        datos["fc_max"] = _dato(top.max_hr, "actividades", f"{when}, «{top.name or 'entreno'}» (id {top.id})")
    else:
        datos["fc_max"] = _dato(thr.hr_max, "edad" if thr.hr_max else None)

    lthr_test = active_test(session, user_id, "running", "lthr")
    pace_test = active_test(session, user_id, "running", "threshold_pace_s_km")
    watch_lthr = next((a for a in reversed(activities) if a.metrics.get("lthr")), None)
    if lthr_test:
        datos["fc_umbral"] = _dato(lthr_test.results["lthr"], "test")
    elif watch_lthr:
        datos["fc_umbral"] = _dato(watch_lthr.metrics["lthr"], "reloj",
                                   watch_lthr.start_time.date().strftime("%d/%m/%Y"))  # fmt: skip
    else:
        datos["fc_umbral"] = _dato(thr.lthr, "estimada" if thr.lthr else None)
    if pace_test:
        pace = round(pace_test.results["threshold_pace_s_km"])
        datos["ritmo_umbral"] = _dato(f"{pace // 60}:{pace % 60:02d} /km", "test")
    watch_vo2 = next((a for a in reversed(activities) if a.metrics.get("vo2max")), None)
    if watch_vo2:
        datos["vo2max"] = _dato(watch_vo2.metrics["vo2max"], "reloj", watch_vo2.start_time.date().strftime("%d/%m/%Y"))
    rests = session.exec(
        select(DailyMetric).where(DailyMetric.user_id == user_id).order_by(col(DailyMetric.day).desc()).limit(30)
    ).all()
    if any(r.metrics.get("resting_hr") for r in rests):
        datos["fc_reposo"] = _dato(round(thr.hr_rest), "reloj", "mediana de los últimos 30 días")

    labels = {"fecha_nacimiento": "fecha de nacimiento", "sexo": "sexo", "peso_kg": "peso", "altura_cm": "altura",
              "fc_max": "FC máxima"}  # fmt: skip
    missing = [label for key, label in labels.items() if datos[key]["origen"] in (None, "edad")]
    if datos["fc_umbral"]["origen"] in (None, "estimada") and "ritmo_umbral" not in datos:
        missing.append("FC o ritmo umbral (solo si los conoce de un test o su reloj)")
    detected = [key for key, d in datos.items() if d["origen"] in ("garmin", "actividades", "reloj")]
    running = session.exec(
        select(SyncRun.id).where(
            SyncRun.user_id == user_id,
            SyncRun.status == SyncStatus.RUNNING,
            SyncRun.started_at >= datetime.now(UTC) - timedelta(hours=2),
        )  # fmt: skip
    ).first()
    return {
        "datos": datos,
        "detectados": detected,
        "faltan": missing,
        "actividades": len(activities),
        "sincronizando": running is not None,
    }


def tool_memoria(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    s = settings(session, user_id)
    return "Tu ficha", {
        "datos": [{"id": m.id, "categoria": m.category, "dato": m.content, "fecha": m.created_at.date().isoformat()}
                  for m in memories(session, user_id)],
        "perfil": athlete_basics(session, user_id),
        "consentimiento_salud": s.health_consent,
        "entrevista_hecha": bool(s.interview_done_at),
        "categorias": CATEGORIES,
    }  # fmt: skip


def tool_guardar(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    from app.services.ai_tools import ToolError

    try:
        m = save_memory(session, user_id, args.get("categoria", ""), args.get("dato", ""), "ia",
                        args.get("reemplaza_id"))  # fmt: skip
    except CoachError as exc:
        raise ToolError(str(exc)) from exc
    action = "corregido" if args.get("reemplaza_id") else "guardado"
    return f"Guardado en tu ficha: {m.content[:60]}", {"ok": True, "efecto": _memory_effect(action, m)}


def tool_olvidar(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    from app.services.ai_tools import ToolError

    try:
        m = forget(session, user_id, int(args.get("id") or 0))
    except (CoachError, ValueError) as exc:
        raise ToolError(str(exc)) from exc
    return f"Quitado de tu ficha: {m.content[:60]}", {"ok": True, "efecto": _memory_effect("olvidado", m)}


SEXES = {"male": "male", "hombre": "male", "varon": "male", "varón": "male", "female": "female", "mujer": "female"}


def tool_perfil(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    """Completa el perfil con lo que la persona ha dicho (solo los campos que vengan)."""
    from app.models import Sex
    from app.services.ai_tools import ToolError
    from app.services.profile import age_on, get_profile, record_weight

    profile = get_profile(session, user_id)
    changes: dict[str, str] = {}
    if args.get("fecha_nacimiento"):
        try:
            born = date.fromisoformat(str(args["fecha_nacimiento"])[:10])
        except ValueError as exc:
            raise ToolError("La fecha de nacimiento va como AAAA-MM-DD.") from exc
        if not 5 <= age_on(born, date.today()) <= 110:
            raise ToolError("La fecha de nacimiento no es válida.")
        profile.birth_date = born
        changes["Nacimiento"] = born.strftime("%d/%m/%Y")
    if args.get("sexo"):
        sex = SEXES.get(str(args["sexo"]).strip().lower())
        if not sex:
            raise ToolError("El sexo va como «male» o «female».")
        profile.sex = Sex(sex)
        changes["Sexo"] = "hombre" if sex == "male" else "mujer"
    numbers = (("peso_kg", "weight_kg", "Peso", 20, 300, "kg"), ("altura_cm", "height_cm", "Altura", 100, 250, "cm"))
    for key, field, label, low, high, unit in numbers:
        if args.get(key) is None:
            continue
        try:
            value = round(float(args[key]), 1)
        except (TypeError, ValueError) as exc:
            raise ToolError(f"{key} debe ser un número.") from exc
        if not low < value < high:
            raise ToolError(f"{key} fuera de rango ({low}–{high} {unit}).")
        if field == "weight_kg" and value != profile.weight_kg:
            record_weight(session, user_id, value, "manual")
        setattr(profile, field, value)
        changes[label] = f"{value:g} {unit}"
    if not changes:
        raise ToolError("No hay ningún dato del perfil que guardar.")
    profile.source = "manual"
    session.add(profile)
    session.commit()
    text = ", ".join(f"{k.lower()} {v}" for k, v in changes.items())
    return f"Perfil actualizado: {text}", {"ok": True, "efecto": {"tipo": "perfil", "cambios": changes}}


def _pace_s(value: object) -> int | None:
    """Ritmo «4:30» (min:s por km) o en segundos."""
    if value is None or value == "":
        return None
    text = str(value).strip()
    if ":" in text:
        minutes, seconds = text.split(":", 1)
        return int(minutes) * 60 + int(seconds)
    return int(float(text))


def tool_umbrales(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    """Guarda como test manual (confirmado) los valores de carrera que la persona conoce."""
    from app.services import performance_tests as pt
    from app.services.ai_tools import ToolError

    try:
        values = {
            "hr_max": int(args["fc_max"]) if args.get("fc_max") else None,
            "lthr": int(args["fc_umbral"]) if args.get("fc_umbral") else None,
            "threshold_pace_s_km": _pace_s(args.get("ritmo_umbral")),
            "vo2max": float(args["vo2max"]) if args.get("vo2max") else None,
        }
        day = date.fromisoformat(str(args["fecha"])[:10]) if args.get("fecha") else date.today()
    except (TypeError, ValueError) as exc:
        raise ToolError("Formato: FC en ppm, ritmo «m:ss», VO2max en ml/kg/min y fecha AAAA-MM-DD.") from exc
    if day > date.today():
        raise ToolError("La fecha no puede ser futura.")
    try:
        row = pt.manual_test(session, user_id, "running", day, values, "Dato de la entrevista con el entrenador")
    except pt.TestError as exc:
        raise ToolError(str(exc)) from exc
    labels = {"hr_max": ("FC máx.", "{:g} ppm"), "lthr": ("FC umbral", "{:g} ppm"), "vo2max": ("VO2max", "{:g}")}
    changes = {labels[k][0]: labels[k][1].format(v) for k, v in values.items() if v is not None and k in labels}
    if values["threshold_pace_s_km"]:
        pace = values["threshold_pace_s_km"]
        changes["Ritmo umbral"] = f"{pace // 60}:{pace % 60:02d} /km"
    text = ", ".join(f"{k} {v}" for k, v in changes.items())
    effect = {"tipo": "umbrales", "id": row.id, "cambios": changes}
    return f"Umbrales guardados: {text}", {"ok": True, "efecto": effect}


def tool_terminar_entrevista(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    row = settings(session, user_id)
    row.interview_done_at = datetime.now(UTC)
    session.add(row)
    session.commit()
    return "Entrevista terminada", {"ok": True, "efecto": {"tipo": "entrevista", "accion": "terminada"}}


def tool_proponer(session: Session, user_id: int, args: dict) -> tuple[str, dict]:
    from app.services.ai_tools import ToolError

    try:
        p = propose(session, user_id, args)
    except CoachError as exc:
        raise ToolError(str(exc)) from exc
    planned = session.get(PlannedSession, p.planned_session_id)
    summary = describe(p, planned)
    return f"Propuesta: {summary[:60]}", {
        "ok": True,
        "nota": "La persona verá la propuesta con botones para aceptarla o rechazarla. No digas que ya está hecho.",
        "efecto": {"tipo": "propuesta", "id": p.id, "sesion_id": p.planned_session_id, "resumen": summary,
                   "motivo": p.reason},
    }  # fmt: skip


def checkin_week(today: date) -> date:
    """Lunes de la semana que se revisa (el domingo se revisa la semana en curso)."""
    return today - timedelta(days=today.weekday())
