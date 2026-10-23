"""
Test de lactato escalonado: umbrales a partir del lactato de cada escalón.

Cada escalón trae su intensidad (velocidad en m/s para correr o vatios en bici), su FC y el lactato
(mmol/L) medido al final. Se calculan:

- **LT1** (umbral aeróbico): la intensidad a la que el lactato sube 0,5 mmol/L por encima del basal
  (el menor de los dos primeros escalones). Es el límite alto de la Z2.
- **LT2** (umbral anaeróbico) con dos métodos:
  - **Dmax modificado** (Bishop 1998): sobre la curva ajustada (polinomio de grado 3), el punto más alejado
    de la recta que une el último escalón antes de la subida de >0,4 mmol/L con el último escalón.
  - **OBLA 4 mmol/L**: la intensidad a la que se cruzan 4 mmol/L (referencia clásica; en gente muy
    entrenada suele quedar por encima de su umbral real).
  Manda el Dmax modificado si sale dentro del rango del test; si no, OBLA.

La FC de cada umbral se interpola entre escalones. Sin numpy: el ajuste cúbico se resuelve con las
ecuaciones normales (4×4) por eliminación de Gauss.
"""

from dataclasses import dataclass

MIN_STEPS = 4
LT1_RISE = 0.5
DMAX_RISE = 0.4
OBLA = 4.0
LACTATE_RANGE = (0.3, 25.0)


class LactateError(ValueError):
    """Los escalones no permiten calcular nada (pocos, desordenados o valores imposibles)."""


@dataclass(frozen=True)
class Step:
    intensity: float  # m/s (carrera) o W (bici)
    lactate: float
    hr: float | None = None


def _interp(x0: float, y0: float, x1: float, y1: float, y: float) -> float:
    return x0 + (y - y0) * (x1 - x0) / (y1 - y0) if y1 != y0 else x0


def _crossing(steps: list[Step], level: float) -> float | None:
    """Intensidad a la que el lactato cruza `level` por primera vez (interpolación lineal)."""
    for a, b in zip(steps, steps[1:], strict=False):
        if a.lactate < level <= b.lactate:
            return _interp(a.intensity, a.lactate, b.intensity, b.lactate, level)
    return None


def hr_at(steps: list[Step], x: float) -> float | None:
    """FC interpolada a una intensidad (entre los escalones con FC)."""
    pts = [(s.intensity, s.hr) for s in steps if s.hr]
    for (x0, h0), (x1, h1) in zip(pts, pts[1:], strict=False):
        if x0 <= x <= x1:
            return h0 + (h1 - h0) * (x - x0) / (x1 - x0) if x1 != x0 else h0
    return None


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        if abs(m[col][col]) < 1e-12:
            raise LactateError("No se puede ajustar la curva con estos escalones.")
        for r in range(n):
            if r != col:
                f = m[r][col] / m[col][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col], strict=True)]
    return [m[i][n] / m[i][i] for i in range(n)]


def cubic_fit(xs: list[float], ys: list[float]) -> list[float]:
    """Coeficientes [a0, a1, a2, a3] del polinomio de grado 3 por mínimos cuadrados (x centrada)."""
    a = [[sum(x ** (i + j) for x in xs) for j in range(4)] for i in range(4)]
    b = [sum(y * x**i for x, y in zip(xs, ys, strict=True)) for i in range(4)]
    return _solve(a, b)


def _poly(c: list[float], x: float) -> float:
    return c[0] + c[1] * x + c[2] * x**2 + c[3] * x**3


def mod_dmax(steps: list[Step]) -> float | None:
    """LT2 por Dmax modificado (None si la curva no lo permite)."""
    start = next((i for i in range(len(steps) - 1) if steps[i + 1].lactate - steps[i].lactate > DMAX_RISE), None)
    if start is None or start >= len(steps) - 2:
        return None
    x0 = steps[0].intensity
    span = steps[-1].intensity - x0 or 1.0
    xs = [(s.intensity - x0) / span for s in steps]  # escalado a 0-1: sistema mejor condicionado
    c = cubic_fit(xs, [s.lactate for s in steps])
    ax, ay = xs[start], _poly(c, xs[start])
    bx, by = xs[-1], _poly(c, xs[-1])
    best_x, best_d = None, 0.0
    for k in range(1, 400):
        x = ax + (bx - ax) * k / 400
        # Distancia (con signo) a la recta A-B: la curva queda por debajo de la cuerda.
        d = ((by - ay) * x - (bx - ax) * _poly(c, x) + bx * ay - by * ax) / ((by - ay) ** 2 + (bx - ax) ** 2) ** 0.5
        if d > best_d:
            best_x, best_d = x, d
    return x0 + best_x * span if best_x is not None else None


def analyze(raw: list[Step]) -> tuple[dict, list[dict]]:
    """
    Umbrales del test.

    Returns:
        (resultados en unidades de intensidad, comprobaciones)

    Raises:
        LactateError: menos de 4 escalones válidos o lactatos imposibles.
    """
    steps = sorted((s for s in raw if s.intensity > 0), key=lambda s: s.intensity)
    if len(steps) < MIN_STEPS:
        raise LactateError(f"Hacen falta al menos {MIN_STEPS} escalones con intensidad y lactato.")
    if any(not LACTATE_RANGE[0] <= s.lactate <= LACTATE_RANGE[1] for s in steps):
        raise LactateError("Algún lactato está fuera de lo posible (0,3-25 mmol/L).")
    checks: list[dict] = []

    def check(key: str, ok: bool, message: str) -> None:
        checks.append({"key": key, "ok": ok, "message": message, "critical": False})

    baseline = min(steps[0].lactate, steps[1].lactate)
    lt1 = _crossing(steps, baseline + LT1_RISE)
    obla = _crossing(steps, OBLA)
    dmax = mod_dmax(steps)
    if dmax is not None and not steps[0].intensity <= dmax <= steps[-1].intensity:
        dmax = None
    lt2 = dmax if dmax is not None else obla
    method = "dmax" if dmax is not None else "obla" if obla is not None else None
    check("lt1", lt1 is not None, "Umbral aeróbico (LT1) encontrado." if lt1 else
          "El lactato no llegó a subir 0,5 sobre el basal: empieza más suave.")  # fmt: skip
    check("lt2", lt2 is not None, "Umbral anaeróbico (LT2) encontrado." if lt2 else
          "El lactato no pasó de 4 mmol/L ni se ve la curva: el último escalón debe ser muy duro.")  # fmt: skip
    if lt1 is not None and lt2 is not None:
        check("orden", lt1 < lt2, "LT1 por debajo de LT2, como debe ser." if lt1 < lt2 else
              "LT1 sale por encima de LT2: revisa los valores.")  # fmt: skip
    monotone = sum(b.lactate < a.lactate - 0.3 for a, b in zip(steps, steps[1:], strict=False))
    check("curva", monotone <= 1, "Curva coherente." if monotone <= 1 else
          "El lactato baja varias veces al subir la intensidad: puede haber errores de medida.")  # fmt: skip
    results = {
        "baseline_mmol": round(baseline, 1),
        "lt1": lt1,
        "lt2": lt2,
        "lt2_method": method,
        "obla": obla,
        "dmax": dmax,
        "lt1_hr": round(h) if lt1 and (h := hr_at(steps, lt1)) else None,
        "lt2_hr": round(h) if lt2 and (h := hr_at(steps, lt2)) else None,
        "steps": [{"intensity": s.intensity, "lactate": s.lactate, "hr": s.hr} for s in steps],
    }
    return {k: v for k, v in results.items() if v is not None}, checks
