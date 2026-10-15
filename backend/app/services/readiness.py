"""
Estado de «hoy» para la pantalla de inicio: un semáforo en lenguaje llano que combina
la frescura (TSB = forma − fatiga) y el pico de carga reciente (ACWR, 7 d : 28 d).

Gana la señal más preocupante: un ACWR alto avisa aunque la frescura parezca buena,
porque los saltos bruscos de carga se asocian a más riesgo de lesión (Gabbett 2016).
Es orientativo, no consejo médico.
"""

from dataclasses import dataclass

GOOD, WATCH, ALERT, NODATA = "good", "watch", "alert", "nodata"


@dataclass(frozen=True)
class Readiness:
    status: str
    title: str
    message: str


def readiness(tsb: float | None, acwr: float | None) -> Readiness:
    """
    Traduce frescura y carga reciente a un estado con consejo para hoy.

    Args:
        tsb: Frescura actual (CTL − ATL); None si no hay historial de carga.
        acwr: Relación carga aguda:crónica; None con menos de ~4 semanas de datos.

    Returns:
        Estado (good / watch / alert / nodata), título corto y consejo.
    """
    if tsb is None:
        return Readiness(NODATA, "Sin datos todavía", "Sincroniza tus entrenos para saber cómo llegas a cada día.")
    if (acwr is not None and acwr > 1.5) or tsb < -30:
        return Readiness(
            ALERT,
            "Sobrecargado",
            "Tu carga reciente ha subido mucho por encima de lo habitual. Hoy mejor descanso o algo muy suave.",
        )
    if (acwr is not None and acwr > 1.3) or tsb < -10:
        return Readiness(
            WATCH,
            "Cansado",
            "Llevas varios días de carga. Si toca una sesión intensa, valora suavizarla y cuida el sueño.",
        )
    if tsb > 15:
        return Readiness(
            GOOD,
            "Muy descansado",
            "Estás muy fresco: buen día para una sesión exigente o una prueba. Si dura semanas, perderás forma.",
        )
    if tsb > 5:
        return Readiness(GOOD, "Fresco", "Buen momento para una sesión de calidad.")
    return Readiness(GOOD, "En equilibrio", "Carga y recuperación están equilibradas: sigue tu plan.")
