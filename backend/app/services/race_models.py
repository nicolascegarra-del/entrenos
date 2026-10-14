"""
Modelos de predicción de tiempos de carrera en asfalto (funciones puras).

- Riegel (1981): T2 = T1 · (D2/D1)^b, con b personal estimado por regresión log-log.
- Daniels y Gilbert: VDOT a partir de una marca y tiempo equivalente para otra distancia.
- Tanda (2011): ritmo de maratón a partir de km/semana y ritmo medio de 8 semanas.
"""

import math

DEFAULT_RIEGEL_EXPONENT = 1.06
# Rango plausible del exponente: por debajo sería "mejor en largo que en corto" sin base fisiológica;
# por encima, una caída de rendimiento extrema que suele indicar datos poco representativos.
EXPONENT_BOUNDS = (1.01, 1.15)


def riegel(time_s: float, from_m: float, to_m: float, exponent: float = DEFAULT_RIEGEL_EXPONENT) -> float:
    """Predicción de Riegel: T2 = T1 × (D2 / D1)^exponente."""
    return time_s * (to_m / from_m) ** exponent


def personal_exponent(efforts: list[tuple[float, float]]) -> tuple[float, bool]:
    """
    Exponente de Riegel personal: pendiente de la regresión log(tiempo) ~ log(distancia).

    Args:
        efforts: Mejores marcas (distancia en m, tiempo en s), una por distancia.

    Returns:
        (exponente, es_personal). Si hay menos de 2 distancias o abarcan menos de ×3 (p. ej. solo 1 km
        y milla), devuelve 1,06 por defecto. El resultado se acota a 1,01–1,15.
    """
    points = [(math.log(d), math.log(t)) for d, t in efforts if d > 0 and t > 0]
    distances = [d for d, _ in efforts]
    if len(points) < 2 or max(distances) / min(distances) < 3:
        return DEFAULT_RIEGEL_EXPONENT, False
    mean_x = sum(x for x, _ in points) / len(points)
    mean_y = sum(y for _, y in points) / len(points)
    var_x = sum((x - mean_x) ** 2 for x, _ in points)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / var_x
    return min(max(slope, EXPONENT_BOUNDS[0]), EXPONENT_BOUNDS[1]), True


def vdot(distance_m: float, time_s: float) -> float:
    """VDOT de Daniels a partir de una marca (fórmulas de Daniels y Gilbert)."""
    minutes = time_s / 60
    velocity = distance_m / minutes  # m/min
    vo2 = -4.60 + 0.182258 * velocity + 0.000104 * velocity**2
    fraction = 0.8 + 0.1894393 * math.exp(-0.012778 * minutes) + 0.2989558 * math.exp(-0.1932605 * minutes)
    return vo2 / fraction


def time_for_vdot(distance_m: float, vdot_value: float) -> float:
    """Tiempo equivalente (s) para `distance_m` con un VDOT dado (búsqueda binaria sobre `vdot`)."""
    low, high = distance_m / 10, distance_m  # entre 10 m/s y 1 m/s
    for _ in range(80):
        mid = (low + high) / 2
        if vdot(distance_m, mid) > vdot_value:
            low = mid  # demasiado rápido para ese VDOT: más tiempo
        else:
            high = mid
    return (low + high) / 2


def pace_at_fraction(vdot_value: float, fraction: float) -> float:
    """Ritmo (s/km) cuyo coste de O₂ es `fraction` × VDOT (inversa de la ecuación de Daniels)."""
    vo2 = vdot_value * fraction
    a, b, c = 0.000104, 0.182258, -4.60 - vo2
    velocity = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)  # m/min
    return 1000 / velocity * 60


# Intensidades de Daniels como fracción del VDOT (Daniels' Running Formula).
DANIELS_FRACTIONS = {
    "easy": (0.59, 0.74),
    "marathon": (0.75, 0.84),
    "threshold": (0.83, 0.88),
    "interval": (0.95, 1.00),
    "repetition": (1.05, 1.10),
}


def daniels_paces(vdot_value: float) -> dict[str, tuple[int, int]]:
    """Rangos de ritmo (s/km, de más rápido a más lento) para E, M, T, I y R."""
    return {
        name: (round(pace_at_fraction(vdot_value, hi)), round(pace_at_fraction(vdot_value, lo)))
        for name, (lo, hi) in DANIELS_FRACTIONS.items()
    }


def tanda_marathon_s(km_per_week: float, avg_pace_s_km: float) -> float:
    """
    Tiempo de maratón según Tanda (2011): Pm = 17,1 + 140·e^(−0,0053·K) + 0,55·P (s/km),
    con K = km/semana y P = ritmo medio de entrenamiento de las últimas 8 semanas.
    """
    pace = 17.1 + 140.0 * math.exp(-0.0053 * km_per_week) + 0.55 * avg_pace_s_km
    return pace * 42.195
