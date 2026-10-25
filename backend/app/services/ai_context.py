"""
Contexto para el asistente de IA: instrucciones de sistema y un resumen compacto de los
datos del usuario (estado, carga, análisis, entrenos, plan, objetivos y perfil).

Funciones puras: reciben los datos ya calculados por la API y devuelven texto. Se
envía lo justo para responder bien sin gastar tokens; nunca el email ni el nombre.
"""

from datetime import date

from app.services.es_format import num

SYSTEM_PROMPT = """\
Eres su entrenador personal dentro de APP ENTRENOS, una app que analiza sus entrenamientos con los datos de su reloj.
Tono: cercano y directo, de tú, en español de España. Vas al grano y explicas el porqué sin rollos (normalmente 2–6
frases o una lista corta). Como un buen entrenador, tienes en cuenta TODO lo que sabes de la persona: sus datos y su
ficha («LO QUE SÉ DEL ATLETA», abajo).

Tienes HERRAMIENTAS para consultar todos sus datos sincronizados: actividades de cualquier fecha con vueltas,
parciales por km, tiempo en zonas, series de FC y ritmo, sensaciones y cumplimiento del plan; zonas y umbrales;
progresión (forma, volumen, VO2max, FC en reposo, HRV, sueño, eficiencia, curva de ritmos); marcas y previsiones;
plan y objetivos; día de carrera; salud diaria; lesiones y zapatillas.

Cómo trabajar:
- Antes de responder, consulta con las herramientas los datos que hagan falta. No supongas lo que puedes mirar.
  Para un entreno concreto usa detalle_actividad (los ids de los recientes están abajo; para otros, busca con
  buscar_actividades). Para tendencias usa progresion. Puedes encadenar varias consultas.
- Razona con los datos y responde en tres partes cortas, con estos títulos en negrita:
  **Qué he mirado** (qué actividades o métricas y de qué fechas),
  **Qué dicen tus datos** (cifras concretas: ritmos, FC, zonas, cargas, comparaciones),
  **Conclusión** (tu interpretación y una recomendación práctica). Separa lo que es dato de lo que es opinión.
  Para un saludo o una pregunta sobre la app que no necesita datos, responde directamente sin esas partes.
- Si un dato no existe (el reloj no lo registra o no hay sincronización), dilo y explica qué haría falta.
- No inventes cifras ni sesiones. Cita los valores reales.
- Usa los nombres de la app: «forma física» (CTL), «fatiga» (ATL), «frescura» (TSB = forma física − fatiga),
  «carga reciente frente a la habitual» (ACWR), «nivel de carrera» (VDOT). Puedes poner la sigla entre paréntesis.
- Las recomendaciones siguen la literatura deportiva que usa la app (modelo forma-fatiga de Banister, ACWR de Gabbett,
  ritmos de Daniels, distribución de intensidad ~80/20 de Seiler). Sé prudente: progresión gradual, escuchar al cuerpo.
- No es consejo médico. Ante dolor, lesión, mareos, dolor en el pecho u otros síntomas, recomienda consultar con un
  profesional sanitario y no des pautas de tratamiento.
- No hables de temas ajenos al entrenamiento, la salud deportiva o el uso de la app.

Tu ficha del atleta (memoria):
- Usa siempre su ficha: lesiones previas, disponibilidad, preferencias, condicionantes de salud (p. ej. un
  betabloqueante baja la FC y cambia la lectura de las zonas) y objetivos. Cítala cuando influya en tu respuesta.
- Si para responder bien te falta algo importante que no está en la ficha, PREGÚNTALO (una o dos preguntas cortas,
  nunca un interrogatorio) y responde con lo que sepas mientras tanto.
- Cuando te cuente algo relevante y duradero sobre sí mismo, guárdalo con guardar_en_memoria (una frase clara, en
  tercera persona). Si corrige algo de la ficha, usa reemplaza_id; si ya no es así, olvidar_dato. No guardes lo que
  deduces de los datos del reloj, ni cosas pasajeras («hoy estoy cansado» va en la revisión semanal), ni nada que
  no te haya dicho.
- Lesiones, enfermedades y medicación solo se guardan si dio su consentimiento (está en la ficha). Si no lo dio y
  te cuenta algo de salud, no lo guardes y dile en una frase que puede activarlo en Ajustes → Asistente IA.
- Tras guardar, dilo en una línea al final («Lo apunto en tu ficha: …»).
- Para cambiar el plan, propón con proponer_cambio_plan (usa los ids de plan_y_objetivos) y explica el motivo; NO
  digas que está cambiado: lo confirma la persona con un botón.

Glosario rápido de la app:
- Carga (hrTSS): puntos por entreno según duración y pulso; 1 h a umbral ≈ 100.
- Forma física (CTL): carga media ~6 semanas. Fatiga (ATL): carga media ~7 días.
- Frescura (TSB): >+5 fresco; −10 a +5 equilibrado; <−10 cargado; <−30 sobrecarga. Para competir, +5 a +25.
- ACWR: 0,8–1,3 zona habitual; >1,5 salto brusco con más riesgo de lesión; <0,8 entrenas menos de lo normal.
- Desacople: <5 % en un rodaje constante indica buena base aeróbica para esa duración.
- Cumplimiento del plan: ≥90 % cumplida; 70–90 % cerca; <70 % distinta de lo previsto.
"""


def _clock(seconds: float | None) -> str:
    """Segundos a h:mm:ss o m:ss."""
    if seconds is None:
        return "—"
    s = round(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _pace(distance_m: float | None, duration_s: float) -> str:
    if not distance_m or distance_m < 100:
        return ""
    return f", ritmo {_clock(duration_s / distance_m * 1000)}/km"


def format_context(data: dict, today: date) -> str:
    """
    Convierte los datos del usuario en un bloque de texto para el modelo.

    Args:
        data: Diccionario con las claves `summary`, `insights`, `activities`, `goals` y `profile`
            (cualquiera puede faltar o venir vacía).
        today: Fecha de hoy (para situar al modelo).

    Returns:
        Texto con secciones; las que no tienen datos se omiten.
    """
    lines = [f"DATOS DEL USUARIO (hoy es {today.strftime('%d/%m/%Y')}, {_weekday(today)}):"]

    profile = data.get("profile") or {}
    if any(profile.values()):
        parts = []
        if profile.get("age"):
            parts.append(f"{profile['age']} años")
        if profile.get("sex"):
            parts.append("hombre" if profile["sex"] == "male" else "mujer")
        if profile.get("weight_kg"):
            parts.append(f"{num(profile['weight_kg'], 1)} kg")
        if profile.get("height_cm"):
            parts.append(f"{num(profile['height_cm'], 0)} cm")
        lines.append("\n## Perfil\n" + ", ".join(parts))

    summary = data.get("summary") or {}
    if summary:
        r = summary.get("readiness") or {}
        f = summary.get("fitness") or {}
        week, last = summary.get("this_week") or {}, summary.get("last_week") or {}
        lines.append("\n## Estado de hoy")
        if r:
            lines.append(f"- Cómo llega hoy: {r.get('title')} — {r.get('message')}")
        if f:
            lines.append(
                f"- Forma física (CTL) {num(f['ctl'], 1)}, fatiga (ATL) {num(f['atl'], 1)}, "
                f"frescura (TSB) {num(f['tsb'], 1)} ({summary.get('form_label') or '—'})"
            )
        if r.get("acwr") is not None:
            lines.append(f"- Carga reciente frente a la habitual (ACWR): {num(r['acwr'], 2)}")
        if summary.get("vo2max"):
            lines.append(f"- VO2max (Garmin): {num(summary['vo2max'], 0)} ml/kg/min")
        if summary.get("resting_hr"):
            lines.append(f"- FC en reposo: {num(summary['resting_hr'], 0)} ppm")
        lines.append(
            f"- Esta semana: {num((week.get('distance_m') or 0) / 1000, 1)} km, {_clock(week.get('duration_s'))}, "
            f"{week.get('count', 0)} actividades, carga {num(week.get('load') or 0, 0)}. "
            f"Semana pasada: {num((last.get('distance_m') or 0) / 1000, 1)} km, {last.get('count', 0)} actividades, "
            f"carga {num(last.get('load') or 0, 0)}."
        )
        planned = summary.get("planned_this_week") or []
        if planned:
            lines.append("\n## Plan de esta semana")
            for p in planned:
                state = (
                    f"cumplimiento {num(p['compliance_score'], 0)} %"
                    if p.get("compliance_score") is not None
                    else ("pendiente" if str(p["day"]) >= today.isoformat() else "sin actividad registrada")
                )
                lines.append(f"- {p['day']}: {p['title']} ({p['sport']}) — {state}")

    insights = data.get("insights") or {}
    if insights:
        lines.append("\n## Análisis de la app (últimos 90 días)")
        for g in insights.get("overall") or []:
            lines.append(f"- {g['label']}: {g['title']} [{g['status']}]")
        for key, s in (insights.get("sections") or {}).items():
            if s.get("status") != "nodata":
                lines.append(f"- {key}: {s['title']}. {s['message']}")
        preds = insights.get("predictions") or []
        if preds:
            lines.append(
                "- Tiempos estimados (Riegel): " + "; ".join(f"{p['label']} {_clock(p['time_s'])}" for p in preds)
            )
        paces = insights.get("training_paces")
        if paces:
            lines.append(
                f"- Ritmos (nivel de carrera/VDOT): suave {_clock(paces['easy'][0])}–{_clock(paces['easy'][1])}/km, "
                f"umbral {_clock(paces['threshold'])}/km, intervalos {_clock(paces['interval'])}/km"
            )

    zones = data.get("zones") or {}
    if zones:
        lines.append("\n## Zonas y umbrales vigentes")
        if zones.get("lthr"):
            lines.append(f"- FC umbral {zones['lthr']} ppm ({zones.get('lthr_source') or '—'})")
        if zones.get("threshold_pace"):
            lines.append(f"- Ritmo umbral {zones['threshold_pace']}/km ({zones.get('pace_source') or '—'})")
        if zones.get("hr"):
            lines.append("- Zonas de FC: " + "; ".join(zones["hr"]))

    weeks = data.get("weeks") or []
    if weeks:
        lines.append("\n## Últimas semanas (lunes, km, tiempo, sesiones, carga)")
        for w in weeks:
            lines.append(
                f"- {w['week']}: {num(w['distance_m'] / 1000, 1)} km, {_clock(w['duration_s'])}, "
                f"{w['count']} sesiones, carga {num(w['load'], 0)}"
            )

    activities = data.get("activities") or []
    if activities:
        lines.append("\n## Últimas actividades (id para detalle_actividad)")
        for a in activities:
            hr = f", FC media {num(a['avg_hr'], 0)}" if a.get("avg_hr") else ""
            dist = f"{num(a['distance_m'] / 1000, 2)} km, " if a.get("distance_m") else ""
            race = " [carrera a tope]" if a.get("is_race") else ""
            ref = f"id {a['id']} · " if a.get("id") else ""
            lines.append(
                f"- {ref}{a['day']} {a['sport']} «{a['name']}»: {dist}{_clock(a['duration_s'])}"
                f"{_pace(a.get('distance_m'), a['duration_s'])}{hr}{race}"
            )

    goals = data.get("goals") or []
    if goals:
        lines.append("\n## Objetivos")
        for g in goals:
            target = f", objetivo {_clock(g['target_time_s'])}" if g.get("target_time_s") else ""
            forecast = f", previsión actual {_clock(g['probable_s'])}" if g.get("probable_s") else ""
            result = f", resultado {_clock(g['result_time_s'])}" if g.get("result_time_s") else ""
            lines.append(
                f"- {g['name']}: {num(g['distance_m'] / 1000, 2)} km el {g['race_date']} "
                f"(faltan {g['days_left']} días){target}{forecast}{result}"
            )

    if len(lines) == 1:
        lines.append("Aún no hay datos: el usuario no ha sincronizado entrenamientos.")
    return "\n".join(lines)


def _weekday(day: date) -> str:
    return ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")[day.weekday()]


def system_prompt(context: str) -> str:
    return f"{SYSTEM_PROMPT}\n{context}"


def conversation_title(question: str) -> str:
    """Título de la conversación: el inicio de la primera pregunta, sin cortar palabras."""
    text = " ".join(question.split())
    if len(text) <= 60:
        return text
    return text[:60].rsplit(" ", 1)[0] + "…"


INTERVIEW_PROMPT = """
MODO ENTREVISTA INICIAL: es la primera vez que trabajas con esta persona. Conócela como haría un entrenador:
- Empieza mirando memoria_del_atleta → «perfil»:
  1) Si «actividades» es 0, recomiéndale conectar y sincronizar antes su reloj (Ajustes → Conexiones) para
     proponerle sus datos reales; si «sincronizando» es true, que espere a que termine. Si prefiere seguir, sigue.
  2) Lo detectado («detectados»: perfil de Garmin, sus entrenos o su reloj): enséñalo en una lista corta con
     de dónde sale (p. ej. «FC máx. 188 ppm, en tu entreno del 12/05/2026 “Series 6×1000”») y pregunta si está
     conforme. Si lo confirma, no guardes nada (se sigue actualizando solo con los entrenos nuevos); si lo
     corrige, guarda su valor con actualizar_perfil o guardar_umbrales.
  3) Lo que falta («faltan»): pregúntalo de uno en uno o dos explicando para qué sirve (edad → FC máx. y
     comparativas; peso → calorías; altura → zancada; FC máx. y umbral → zonas y carga) y guárdalo con
     actualizar_perfil (nacimiento, sexo, peso, altura) o guardar_umbrales (FC máx., FC o ritmo umbral, VO2max).
     Los umbrales solo si los conoce de un test, una prueba de esfuerzo o su reloj: si no, dile que la app los
     irá calculando con sus entrenos y sigue. Nunca inventes ni estimes tú un valor para guardarlo.
- Después, pregunta de una en una (como mucho dos cosas por mensaje), en este orden y saltando lo que ya esté en
  la ficha: 1) años corriendo y otros deportes; 2) lesiones o molestias de los últimos años (solo si hay
  consentimiento de salud; si no, pregunta si quiere activarlo para tenerlas en cuenta); 3) salud que afecte al
  entreno (medicación como betabloqueantes, asma…; mismo criterio); 4) disponibilidad: días, horas, dónde entrena
  (pista, montaña, cinta, gimnasio); 5) objetivos a medio y largo plazo; 6) qué sesiones le gustan y cuáles odia;
  7) trabajo, sueño y estrés habituales.
- Tras cada respuesta, guarda lo importante con guardar_en_memoria y pasa a la siguiente pregunta.
- Mensajes cortos. Si quiere parar, para.
- Al final (o si quiere parar), resume en 3-5 viñetas lo que has aprendido y cómo lo vas a usar, y llama a
  terminar_entrevista.
"""


def interview_prompt() -> str:
    return INTERVIEW_PROMPT
