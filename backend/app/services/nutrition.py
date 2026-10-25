"""
Nutrición deportiva determinista: funciones puras, sin BD ni IA, con base científica citada.

Todo devuelve dataclasses tipadas con rangos y un valor recomendado. Los textos van en español y siempre
acompañados de `DISCLAIMER`: es orientación general, no un plan dietético individual.

Fuentes principales (detalle en `REFERENCES`):
- Gasto basal: Mifflin-St Jeor (Mifflin et al. 1990); con masa magra, Cunningham (1980).
- Gasto del entreno: MET del Compendium of Physical Activities (Ainsworth et al. 2011).
- Hidratos, proteína y grasa diarios: ACSM/AND/DC 2016 (Thomas et al.) e IOC 2011 (Burke et al.).
- Hidratos durante el ejercicio: Jeukendrup 2014.
- Hidratación: ACSM 2007 (Sawka et al.).
- Cafeína: ISSN 2021 (Guest et al.).
- Disponibilidad energética y RED-S: IOC 2018 y 2023 (Mountjoy et al.).
"""

import math
from dataclasses import dataclass, field

# ─── Referencias y aviso ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Reference:
    """Cita bibliográfica breve."""

    author: str
    year: int
    title: str

    def __str__(self) -> str:
        return f"{self.author} {self.year} · {self.title}"


REFERENCES: dict[str, Reference] = {
    "mifflin1990": Reference("Mifflin et al.", 1990, "A new predictive equation for resting energy expenditure"),
    "cunningham1980": Reference("Cunningham", 1980, "A reanalysis of the factors influencing basal metabolic rate"),
    "ainsworth2011": Reference("Ainsworth et al.", 2011, "Compendium of Physical Activities"),
    "acsm2016": Reference("Thomas, Erdman y Burke (ACSM/AND/DC)", 2016, "Nutrition and Athletic Performance"),
    "ioc2011": Reference("Burke et al. (IOC)", 2011, "Carbohydrates for training and competition"),
    "issn2017": Reference("Jäger et al. (ISSN)", 2017, "Position stand: protein and exercise"),
    "jeukendrup2014": Reference("Jeukendrup", 2014, "A step towards personalized sports nutrition: carbohydrate "
                                                    "intake during exercise"),
    "acsm2007": Reference("Sawka et al. (ACSM)", 2007, "Exercise and fluid replacement"),
    "issn2021": Reference("Guest et al. (ISSN)", 2021, "Position stand: caffeine and exercise performance"),
    "ioc2018": Reference("Mountjoy et al. (IOC)", 2018, "Consensus statement on RED-S: 2018 update"),
    "ioc2023": Reference("Mountjoy et al. (IOC)", 2023, "Consensus statement on Relative Energy Deficiency in Sport"),
}  # fmt: skip

DISCLAIMER = (
    "Orientación general, no sustituye a un dietista-nutricionista. Si tienes alguna enfermedad, tomas "
    "medicación, estás embarazada o has tenido problemas con la comida, consulta a un profesional sanitario."
)


def _refs(*keys: str) -> list[str]:
    return [str(REFERENCES[k]) for k in keys]


# ─── Tipos comunes ───────────────────────────────────────────────────────────

INTENSITIES = ("suave", "moderada", "alta", "muy_alta")
_INTENSITY_ALIASES = {
    "easy": "suave", "baja": "suave", "low": "suave", "recuperacion": "suave", "recuperación": "suave",
    "moderate": "moderada", "media": "moderada", "medium": "moderada",
    "hard": "alta", "high": "alta", "intensa": "alta",
    "very_hard": "muy_alta", "muy alta": "muy_alta", "maxima": "muy_alta", "máxima": "muy_alta",
}  # fmt: skip

# MET de carrera a pie (Ainsworth et al. 2011): trote ~7, ~9,7 km/h ≈ 9,8, ~11 km/h ≈ 11,5, ~13 km/h ≈ 12,8.
MET_BY_INTENSITY = {"suave": 7.0, "moderada": 9.8, "alta": 11.5, "muy_alta": 12.8}
# Peso de la intensidad para clasificar la carga del día (heurística propia sobre las categorías ACSM 2016).
LOAD_WEIGHT = {"suave": 0.75, "moderada": 1.0, "alta": 1.25, "muy_alta": 1.5}

LOAD_LEVELS = ("descanso", "ligero", "moderado", "alto", "muy_alto")
# Hidratos diarios en g/kg por nivel de carga: (mínimo, máximo, recomendado). ACSM/AND/DC 2016, IOC 2011.
CARBS_G_KG = {
    "descanso": (3.0, 5.0, 3.0),
    "ligero": (3.0, 5.0, 4.0),
    "moderado": (5.0, 7.0, 6.0),
    "alto": (6.0, 10.0, 8.0),
    "muy_alto": (8.0, 12.0, 10.0),
}
PROTEIN_G_KG = (1.2, 2.0, 1.6)  # ACSM 2016 / ISSN 2017
PROTEIN_PER_MEAL_G_KG = 0.3
FAT_MIN_SHARE = 0.20  # ≥ 20 % de la energía (ACSM 2016)
FAT_MAX_SHARE = 0.35
GEL_CARBS_G = 25  # gel típico; parametrizable en `during_session`
SODIUM_MG_H = (300, 600)


@dataclass(frozen=True)
class Range:
    """Rango orientativo con un valor recomendado dentro de él."""

    low: float
    high: float
    recommended: float
    unit: str


def _positive(name: str, value: float) -> float:
    if value is None or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} debe ser mayor que 0.")
    return float(value)


def _non_negative(name: str, value: float) -> float:
    if value is None or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} no puede ser negativo.")
    return float(value)


def normalize_intensity(intensity: str) -> str:
    """Normaliza la intensidad a `suave` / `moderada` / `alta` / `muy_alta` (admite alias en inglés)."""
    key = (intensity or "").strip().lower()
    key = _INTENSITY_ALIASES.get(key, key)
    if key not in INTENSITIES:
        raise ValueError(f"Intensidad desconocida: {intensity!r}. Usa una de {', '.join(INTENSITIES)}.")
    return key


def _scaled(r: tuple[float, float, float], factor: float, unit: str, ndigits: int = 0) -> Range:
    return Range(round(r[0] * factor, ndigits), round(r[1] * factor, ndigits), round(r[2] * factor, ndigits), unit)


# ─── Gasto energético ────────────────────────────────────────────────────────


def bmr(sex: str, weight_kg: float, height_cm: float, age: float, lean_mass_kg: float | None = None) -> float:
    """
    Gasto energético en reposo (kcal/día).

    - Sin masa magra: Mifflin-St Jeor (Mifflin et al. 1990): 10·peso + 6,25·altura − 5·edad + 5 (hombre) o − 161
      (mujer).
    - Con masa magra (kg): Cunningham (1980): 500 + 22·masa magra; más precisa en deportistas.

    Raises:
        ValueError: si peso, altura, edad o masa magra no son positivos, la masa magra supera el peso o el sexo
            no es reconocido.
    """
    w = _positive("El peso", weight_kg)
    if lean_mass_kg is not None:
        lbm = _positive("La masa magra", lean_mass_kg)
        if lbm > w:
            raise ValueError("La masa magra no puede ser mayor que el peso.")
        return round(500 + 22 * lbm, 1)
    h = _positive("La altura", height_cm)
    a = _positive("La edad", age)
    s = (sex or "").strip().lower()
    if s in ("m", "male", "hombre", "h", "varon", "varón", "masculino"):
        offset = 5
    elif s in ("f", "female", "mujer", "femenino"):
        offset = -161
    else:
        raise ValueError("Sexo no reconocido: usa «hombre» o «mujer».")
    return round(10 * w + 6.25 * h - 5 * a + offset, 1)


def exercise_kcal(duration_min: float, weight_kg: float, intensity: str = "moderada") -> float:
    """
    Gasto neto estimado de una sesión (kcal): (MET − 1) × peso × horas (Ainsworth et al. 2011).

    Se resta 1 MET (el reposo) porque el basal ya está contado en el resto del día.
    """
    minutes = _non_negative("La duración", duration_min)
    w = _positive("El peso", weight_kg)
    met = MET_BY_INTENSITY[normalize_intensity(intensity)]
    return round((met - 1) * w * minutes / 60, 1)


def day_load_level(planned_minutes: float, intensity: str = "moderada") -> str:
    """
    Nivel de carga del día para elegir los hidratos (categorías de ACSM/AND/DC 2016 e IOC 2011).

    Se ponderan los minutos por la intensidad (suave ×0,75, moderada ×1, alta ×1,25, muy alta ×1,5) y:
    0 → `descanso`; < 45 → `ligero`; ≤ 90 (~1 h/día) → `moderado`; ≤ 240 (1–3 h) → `alto`;
    > 240 (> 4 h) → `muy_alto`.

    Raises:
        ValueError: si la duración es negativa o la intensidad no existe.
    """
    minutes = _non_negative("La duración planificada", planned_minutes)
    if minutes == 0:
        return "descanso"
    eff = minutes * LOAD_WEIGHT[normalize_intensity(intensity)]
    if eff < 45:
        return "ligero"
    if eff <= 90:
        return "moderado"
    if eff <= 240:
        return "alto"
    return "muy_alto"


# ─── Objetivos diarios ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class DailyTargets:
    load: str
    bmr_kcal: float
    activity_factor: float
    exercise_kcal: float
    exercise_source: str  # "actividad" (kcal reales) | "estimado" (MET) | "ninguno"
    kcal: Range
    carbs_g_kg: Range
    carbs_g: Range
    protein_g_kg: Range
    protein_g: Range
    protein_per_meal_g: float
    meals: int
    fat_g: Range
    fat_pct: float
    notes: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER


def daily_targets(
    sex: str,
    weight_kg: float,
    height_cm: float,
    age: float,
    planned_minutes: float = 0,
    intensity: str = "moderada",
    actual_kcal: float | None = None,
    actual_minutes: float | None = None,
    lean_mass_kg: float | None = None,
    activity_factor: float = 1.4,
) -> DailyTargets:
    """
    Energía y macronutrientes del día según la carga de entrenamiento.

    - kcal = basal × factor de actividad no deportiva (1,2 sedentario … 1,6 trabajo de pie; incluye la
      termogénesis de los alimentos) + gasto del entreno. Si hay kcal reales de la actividad se usan,
      descontando el basal de esos minutos; si no, se estiman con MET (Ainsworth 2011). Rango ±10 %.
    - Hidratos g/kg por carga: ligero 3–5, moderado 5–7, alto 6–10, muy alto 8–12 (ACSM/AND/DC 2016,
      IOC 2011).
    - Proteína 1,2–2,0 g/kg (recomendado 1,6) en 4 tomas de ~0,3 g/kg (ACSM 2016, ISSN 2017).
    - Grasa: lo que queda de energía, nunca < 20 % ni > 35 %. Si hidratos y proteína no dejan el 20 % para la
      grasa, se sube la energía recomendada para respetarlo (no se recortan hidratos).

    Raises:
        ValueError: si algún dato antropométrico no es positivo, la duración es negativa o el factor de
            actividad está fuera de 1,1–2,0.
    """
    w = _positive("El peso", weight_kg)
    if not 1.1 <= activity_factor <= 2.0:
        raise ValueError("El factor de actividad debe estar entre 1,1 y 2,0.")
    base = bmr(sex, w, height_cm, age, lean_mass_kg)
    load = day_load_level(planned_minutes, intensity)
    notes: list[str] = []
    if actual_kcal is not None:
        kcal_act = _non_negative("Las kcal de la actividad", actual_kcal)
        minutes = _non_negative("La duración", actual_minutes if actual_minutes is not None else planned_minutes)
        ex = round(max(0.0, kcal_act - base * minutes / 1440), 1)
        source = "actividad"
    elif planned_minutes > 0:
        ex = exercise_kcal(planned_minutes, w, intensity)
        source = "estimado"
    else:
        ex, source = 0.0, "ninguno"
    kcal_est = base * activity_factor + ex

    carbs_kg = CARBS_G_KG[load]
    carbs = _scaled(carbs_kg, w, "g")
    protein = _scaled(PROTEIN_G_KG, w, "g")
    fixed_kcal = carbs.recommended * 4 + protein.recommended * 4
    if fixed_kcal > kcal_est * (1 - FAT_MIN_SHARE):
        kcal_rec = fixed_kcal / (1 - FAT_MIN_SHARE)
        notes.append(
            "Para cubrir los hidratos y la proteína recomendados con al menos un 20 % de grasa, la energía del "
            "día sube por encima de la estimación. Guíate también por el hambre y el rendimiento."
        )
    else:
        kcal_rec = kcal_est
    fat_rec = (kcal_rec - fixed_kcal) / 9
    fat_rec = min(max(fat_rec, FAT_MIN_SHARE * kcal_rec / 9), FAT_MAX_SHARE * kcal_rec / 9)
    fat = Range(round(FAT_MIN_SHARE * kcal_rec / 9), round(FAT_MAX_SHARE * kcal_rec / 9), round(fat_rec), "g")
    if load in ("alto", "muy_alto"):
        notes.append("Día exigente: reparte los hidratos antes, durante y después del entreno.")
    if load == "descanso":
        notes.append("Día de descanso: hidratos en la parte baja del rango, proteína igual que los demás días.")
    meals = 4
    return DailyTargets(
        load=load,
        bmr_kcal=base,
        activity_factor=activity_factor,
        exercise_kcal=ex,
        exercise_source=source,
        kcal=Range(round(kcal_rec * 0.9), round(kcal_rec * 1.1), round(kcal_rec), "kcal"),
        carbs_g_kg=Range(*carbs_kg, "g/kg"),
        carbs_g=carbs,
        protein_g_kg=Range(*PROTEIN_G_KG, "g/kg"),
        protein_g=protein,
        protein_per_meal_g=round(PROTEIN_PER_MEAL_G_KG * w),
        meals=meals,
        fat_g=fat,
        fat_pct=round(fat_rec * 9 / kcal_rec * 100, 1),
        notes=notes,
        references=_refs(
            "mifflin1990" if lean_mass_kg is None else "cunningham1980", "ainsworth2011", "acsm2016", "ioc2011",
            "issn2017",
        ),
    )  # fmt: skip


# ─── Durante el ejercicio ────────────────────────────────────────────────────


@dataclass(frozen=True)
class CarbsBand:
    """Banda de hidratos por hora según la duración (Jeukendrup 2014)."""

    key: str  # "nada" | "enjuague" | "30-60" | "hasta-90"
    low: int
    high: int
    note: str


def carbs_band(duration_min: float) -> CarbsBand:
    """
    Hidratos por hora según la duración (Jeukendrup 2014):
    < 45 min nada; 45–75 min enjuague bucal o pequeñas cantidades; hasta 2,5 h 30–60 g/h;
    > 2,5 h hasta 90 g/h con mezcla glucosa + fructosa (transportadores múltiples).

    Raises:
        ValueError: si la duración es negativa.
    """
    minutes = _non_negative("La duración", duration_min)
    if minutes < 45:
        return CarbsBand("nada", 0, 0, "Menos de 45 minutos: no hace falta tomar nada; agua si tienes sed.")
    if minutes <= 75:
        return CarbsBand(
            "enjuague",
            0,
            30,
            "Entre 45 y 75 minutos: basta un enjuague con bebida isotónica o un pequeño sorbo; no es necesario comer.",
        )
    if minutes <= 150:
        return CarbsBand("30-60", 30, 60, "Toma hidratos desde los 30–40 minutos, repartidos.")
    return CarbsBand("hasta-90", 60, 90, "Sesión larga: hidratos desde el principio y cada 20–30 minutos; por "
                                         "encima de 60 g/h usa mezcla de glucosa y fructosa. Ensáyalo en los "
                                         "entrenos.")  # fmt: skip


def fluid_ml_h(temp_c: float | None) -> tuple[int, int]:
    """Líquido orientativo por hora según la temperatura (ACSM 2007): 400–800 ml/h."""
    t = 15 if temp_c is None else temp_c
    return (400, 500) if t < 15 else (500, 700) if t < 25 else (600, 800)


def _plural(name: str) -> str:
    return name + ("s" if name[-1:].lower() in "aeiouáéíóú" else "es")


@dataclass(frozen=True)
class DuringSession:
    duration_min: float
    band: str
    carbs_g_h: Range
    total_carbs_g: float
    multiple_transportable: bool
    units: int
    unit_carbs_g: float
    interval_min: int | None
    first_intake_min: int | None
    text: str
    references: list[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER


def during_session(
    duration_min: float, intensity: str = "moderada", product_carbs_g: float = GEL_CARBS_G, product: str = "gel"
) -> DuringSession:
    """
    Hidratos durante una sesión (Jeukendrup 2014) y pauta práctica en unidades de producto.

    Dentro de la banda, el valor recomendado sube con la intensidad (suave → parte baja, alta → parte alta).
    Las unidades cubren el recomendado desde la primera toma (30 min en sesiones > 2,5 h, 40 min si no).

    Raises:
        ValueError: si la duración es negativa o los gramos del producto no son positivos.
    """
    unit_g = _positive("Los gramos de hidratos del producto", product_carbs_g)
    level = normalize_intensity(intensity)
    band = carbs_band(duration_min)
    share = {"suave": 0.0, "moderada": 0.5, "alta": 1.0, "muy_alta": 1.0}[level]
    rec = 0 if band.key in ("nada", "enjuague") else round(band.low + (band.high - band.low) * share)
    first = None if rec == 0 else (30 if band.key == "hasta-90" else 40)
    fuel_h = max(0.0, duration_min - (first or 0)) / 60 if first is not None else 0.0
    total = round(rec * fuel_h)
    units = max(1, round(total / unit_g)) if rec else 0
    interval = max(15, round(fuel_h * 60 / units)) if units else None
    if units:
        plural = product if units == 1 else _plural(product)
        text = (f"≈ {units} {plural} de {unit_g:g} g (uno cada ~{interval} min desde el minuto {first}), "
                f"o bebida con hidratos equivalente: unos {rec} g/h. {band.note}")  # fmt: skip
    else:
        text = band.note
    return DuringSession(
        duration_min=duration_min,
        band=band.key,
        carbs_g_h=Range(band.low, band.high, rec, "g/h"),
        total_carbs_g=total,
        multiple_transportable=rec > 60,
        units=units,
        unit_carbs_g=unit_g,
        interval_min=interval,
        first_intake_min=first,
        text=text,
        references=_refs("jeukendrup2014"),
    )


# ─── Hidratación ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Hydration:
    sweat_l: float
    sweat_rate_l_h: float
    loss_pct: float
    within_target: bool
    weight_gain: bool
    drink_to_stay_under_2pct_ml_h: int
    rehydrate_l: Range
    sodium_mg_h: Range
    text: str
    references: list[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER


def hydration(
    weight_before_kg: float, weight_after_kg: float, fluid_l: float, duration_h: float, urine_l: float = 0.0
) -> Hydration:
    """
    Tasa de sudoración con pesaje antes/después (ACSM 2007, Sawka et al.).

    sudor (L) = peso antes − peso después + líquido bebido − orina (1 kg ≈ 1 L). Objetivo: perder < 2 % del
    peso. Tras el ejercicio, reponer 1,25–1,5 L por kg perdido. Sodio orientativo 300–600 mg/h en sesiones
    largas o con mucho sudor.

    Raises:
        ValueError: si algún peso o la duración no son positivos, o el líquido/orina son negativos.
    """
    before = _positive("El peso antes", weight_before_kg)
    after = _positive("El peso después", weight_after_kg)
    hours = _positive("La duración", duration_h)
    drunk = _non_negative("El líquido bebido", fluid_l)
    urine = _non_negative("La orina", urine_l)
    lost_kg = before - after
    sweat = max(0.0, lost_kg + drunk - urine)
    loss_pct = round(lost_kg / before * 100, 2)
    allowed = 0.02 * before
    drink_needed = max(0.0, sweat - allowed) / hours * 1000
    rehyd = Range(round(max(0.0, lost_kg) * 1.25, 2), round(max(0.0, lost_kg) * 1.5, 2),
                  round(max(0.0, lost_kg) * 1.5, 2), "L")  # fmt: skip
    if lost_kg < 0:
        text = ("Has ganado peso: bebiste más de lo que sudaste. Beber de más puede bajar el sodio en sangre "
                "(hiponatremia); bebe según la sed.")  # fmt: skip
    elif loss_pct >= 2:
        text = (f"Perdiste un {loss_pct:.1f} % del peso (objetivo < 2 %). En sesiones parecidas bebe unos "
                f"{round(drink_needed, -1):.0f} ml/h y repón {rehyd.low:g}–{rehyd.high:g} L después.")  # fmt: skip
    else:
        text = f"Perdiste un {loss_pct:.1f} % del peso: dentro del objetivo (< 2 %)."
    return Hydration(
        sweat_l=round(sweat, 2),
        sweat_rate_l_h=round(sweat / hours, 2),
        loss_pct=loss_pct,
        within_target=0 <= loss_pct < 2,
        weight_gain=lost_kg < 0,
        drink_to_stay_under_2pct_ml_h=round(drink_needed),
        rehydrate_l=rehyd,
        sodium_mg_h=Range(*SODIUM_MG_H, 450, "mg/h"),
        text=text,
        references=_refs("acsm2007"),
    )


# ─── Carrera ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FeedPoint:
    time_min: int
    km: float
    carbs_g: float
    note: str = ""


@dataclass(frozen=True)
class RacePlan:
    duration_min: float
    carb_loading: Range | None  # g/día, 36–48 h antes
    carb_loading_g_kg: Range | None
    pre_meal_g: Range
    pre_meal_hours: tuple[int, int]
    caffeine_mg: Range
    caffeine_note: str
    during: DuringSession
    feed_points: list[FeedPoint]
    notes: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER


def _profile_times(profile: list[list[float]], distance_m: float, total_s: float) -> tuple[list[float], list[float]]:
    """Distancia (m, escalada a la carrera) y tiempo acumulado (s) en cada punto, con el coste de la pendiente."""
    from app.services.race_day import grade_factor  # import diferido: race_day importa este módulo

    pts = [(float(p[0]), float(p[1])) for p in profile]
    if len(pts) < 2 or pts[-1][0] <= pts[0][0]:
        raise ValueError("El perfil necesita al menos dos puntos con distancia creciente.")
    if any(b[0] < a[0] for a, b in zip(pts, pts[1:], strict=False)):
        raise ValueError("Las distancias del perfil deben ser crecientes.")
    scale = distance_m / (pts[-1][0] - pts[0][0])
    dist, cost = [0.0], [0.0]
    for (d0, e0), (d1, e1) in zip(pts, pts[1:], strict=False):
        length = d1 - d0
        f = grade_factor((e1 - e0) / length) if length > 0 else 1.0
        dist.append(dist[-1] + length * scale)
        cost.append(cost[-1] + length * scale * f)
    return dist, [c / cost[-1] * total_s for c in cost]


def _climbs(profile: list[list[float]], dist: list[float], min_grade: float = 0.03, min_gain: float = 20.0):
    """Subidas: tramos seguidos con pendiente ≥ 3 % y ≥ 20 m de desnivel. Devuelve índices (inicio, fin)."""
    out, start, gain = [], None, 0.0
    for i in range(1, len(profile)):
        length = profile[i][0] - profile[i - 1][0]
        rise = profile[i][1] - profile[i - 1][1]
        climbing = length > 0 and rise / length >= min_grade
        if climbing:
            start = i - 1 if start is None else start
            gain += rise
        if (not climbing or i == len(profile) - 1) and start is not None:
            end = i if climbing else i - 1
            if gain >= min_gain:
                out.append((start, end))
            start, gain = None, 0.0
    return out


def _interp(xs: list[float], ys: list[float], x: float) -> float:
    for i in range(1, len(xs)):
        if x <= xs[i]:
            span = xs[i] - xs[i - 1]
            return ys[i - 1] + (ys[i] - ys[i - 1]) * ((x - xs[i - 1]) / span if span else 0)
    return ys[-1]


def race_plan(
    distance_m: float,
    expected_time_s: float,
    weight_kg: float,
    profile: list[list[float]] | None = None,
    product_carbs_g: float = GEL_CARBS_G,
    product: str = "gel",
) -> RacePlan:
    """
    Plan nutricional de carrera.

    - Carga de hidratos 10–12 g/kg/día las 36–48 h previas solo si la prueba dura > 90 min (ACSM 2016, IOC 2011).
    - Comida previa: 1–4 g/kg de hidratos entre 1 y 4 h antes (más cantidad cuanto más margen).
    - Cafeína opcional 3–6 mg/kg 30–60 min antes (ISSN 2021); probarla antes en entrenos.
    - Durante: `during_session` a intensidad alta (Jeukendrup 2014), con puntos de toma por tiempo y km.
      Con perfil (`[[distancia_m, altitud_m], …]`, como el `profile` de `route_planner`), el tiempo se reparte
      con el coste de la pendiente (`race_day.grade_factor`) y las tomas que caen en mitad de una subida se
      adelantan al pie de la subida (o se retrasan a la cima si quedarían demasiado juntas).

    Raises:
        ValueError: si distancia, tiempo o peso no son positivos, o el perfil no es válido.
    """
    dist_m = _positive("La distancia", distance_m)
    total_s = _positive("El tiempo previsto", expected_time_s)
    w = _positive("El peso", weight_kg)
    minutes = total_s / 60
    notes: list[str] = []
    if minutes > 90:
        loading_kg = Range(10, 12, 10, "g/kg")
        loading = _scaled((10, 12, 10), w, "g")
        notes.append("Carga de hidratos los 1,5–2 días previos: baja la fibra y la grasa para que quepan.")
    else:
        loading_kg = loading = None
        notes.append("Prueba de menos de 90 minutos: no hace falta carga de hidratos, basta una dieta normal "
                     "rica en hidratos el día anterior.")  # fmt: skip
    during = during_session(minutes, "alta", product_carbs_g, product)

    if profile:
        dist, times = _profile_times(profile, dist_m, total_s)
        climbs = _climbs(profile, dist)
    else:
        dist, times, climbs = [0.0, dist_m], [0.0, total_s], []
    points: list[FeedPoint] = []
    if during.units:
        prev = -math.inf
        for i in range(during.units):
            t = (during.first_intake_min + i * during.interval_min) * 60
            if t >= total_s - 5 * 60:
                break
            note = ""
            d = _interp(times, dist, t)
            for s, e in climbs:
                if dist[s] < d < dist[e]:
                    if times[s] - prev >= 10 * 60:
                        t, d, note = times[s], dist[s], "antes de la subida"
                    else:
                        t, d, note = times[e], dist[e], "al coronar la subida"
                    break
            prev = t
            points.append(FeedPoint(round(t / 60), round(d / 1000, 1), during.unit_carbs_g, note))

    return RacePlan(
        duration_min=round(minutes, 1),
        carb_loading=loading,
        carb_loading_g_kg=loading_kg,
        pre_meal_g=_scaled((1, 4, 2), w, "g"),
        pre_meal_hours=(1, 4),
        caffeine_mg=_scaled((3, 6, 3), w, "mg"),
        caffeine_note=(
            "Opcional: 3–6 mg/kg de cafeína 30–60 min antes. Pruébala antes en entrenos: puede dar "
            "molestias de estómago, nervios o empeorar el sueño."
        ),
        during=during,
        feed_points=points,
        notes=notes,
        references=_refs("acsm2016", "ioc2011", "jeukendrup2014", "issn2021"),
    )


# ─── Recuperación ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Recovery:
    quick: bool
    carbs_g_h: Range | None
    carbs_hours: int
    protein_g: float
    text: str
    references: list[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER


def recovery(next_session_in_h: float, weight_kg: float) -> Recovery:
    """
    Recuperación tras la sesión (ACSM/AND/DC 2016, ISSN 2017).

    Si la siguiente sesión es en < 8 h: 1,0–1,2 g/kg/h de hidratos las primeras 4 h. Siempre ~0,3 g/kg de
    proteína en las 2 h siguientes.

    Raises:
        ValueError: si el peso no es positivo o el tiempo hasta la siguiente sesión es negativo.
    """
    hours = _non_negative("El tiempo hasta la siguiente sesión", next_session_in_h)
    w = _positive("El peso", weight_kg)
    protein = round(PROTEIN_PER_MEAL_G_KG * w)
    if hours < 8:
        carbs = _scaled((1.0, 1.2, 1.1), w, "g/h")
        span = int(min(4, max(1, math.floor(hours)))) if hours >= 1 else 1
        text = (f"Vuelves a entrenar en menos de 8 h: toma unos {carbs.low:g}–{carbs.high:g} g de hidratos por "
                f"hora durante {span} h y unos {protein} g de proteína nada más terminar.")  # fmt: skip
    else:
        carbs, span = None, 0
        text = (f"Hay margen hasta la siguiente sesión: haz tus comidas normales con hidratos y unos {protein} g "
                "de proteína en las 2 h siguientes.")  # fmt: skip
    return Recovery(hours < 8, carbs, span, protein, text, _refs("acsm2016", "issn2017"))


# ─── Disponibilidad energética y RED-S ───────────────────────────────────────


@dataclass(frozen=True)
class EnergyAvailability:
    kcal_per_kg_ffm: float
    level: str  # "optima" | "reducida" | "baja"
    red_s_risk: bool
    text: str
    references: list[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER


def energy_availability(intake_kcal: float, exercise_kcal_value: float, ffm_kg: float) -> EnergyAvailability:
    """
    Disponibilidad energética = (ingesta − gasto del ejercicio) / masa libre de grasa (kcal/kg FFM/día).

    < 30 → baja, riesgo de RED-S (IOC 2018 y 2023); 30–45 → reducida; ≥ 45 → óptima. El aviso recomienda
    acudir a un dietista-nutricionista o a un médico y nunca da cifras de restricción.

    Raises:
        ValueError: si la masa libre de grasa no es positiva o la ingesta/gasto son negativos.
    """
    intake = _non_negative("La ingesta", intake_kcal)
    ex = _non_negative("El gasto del ejercicio", exercise_kcal_value)
    ffm = _positive("La masa libre de grasa", ffm_kg)
    ea = round((intake - ex) / ffm, 1)
    if ea < 30:
        level = "baja"
        text = ("Tu disponibilidad energética parece baja: comes poco para lo que entrenas. Mantenerla así "
                "puede afectar a la salud hormonal, ósea y al rendimiento (RED-S). Te recomendamos consultar "
                "con un dietista-nutricionista o un médico deportivo.")  # fmt: skip
    elif ea < 45:
        level = "reducida"
        text = ("Disponibilidad energética algo justa. Si notas cansancio, lesiones frecuentes o cambios en el "
                "ciclo menstrual, coméntalo con un profesional sanitario.")  # fmt: skip
    else:
        level = "optima"
        text = "Disponibilidad energética adecuada para entrenar y recuperar."
    return EnergyAvailability(ea, level, ea < 30, text, _refs("ioc2018", "ioc2023"))


# ─── Seguridad ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SafetyFlags:
    restricted: bool
    allow_weight_loss: bool
    allow_menus: bool
    reasons: list[str]
    text: str
    disclaimer: str = DISCLAIMER


def safety_flags(
    age: float, pregnant: bool = False, conditions: list[str] | tuple[str, ...] = (),
    eating_disorder_history: bool = False,
) -> SafetyFlags:  # fmt: skip
    """
    Casos en los que no se dan pautas de pérdida de peso ni menús y se deriva a un profesional:
    menores de 18 años, embarazo, historia de trastorno de la conducta alimentaria (TCA) u otras condiciones
    médicas declaradas (diabetes, enfermedad renal, etc.). Criterio de prudencia alineado con IOC 2023.

    Raises:
        ValueError: si la edad no es positiva.
    """
    a = _positive("La edad", age)
    reasons = []
    if a < 18:
        reasons.append("menor de edad")
    if pregnant:
        reasons.append("embarazo")
    if eating_disorder_history:
        reasons.append("antecedentes de trastorno de la conducta alimentaria")
    reasons += [f"condición: {c.strip()}" for c in conditions if c and c.strip()]
    if reasons:
        text = (
            f"Por tu situación ({', '.join(reasons)}) no damos pautas de pérdida de peso ni menús. "
            "Consulta con un dietista-nutricionista o tu médico, que puede adaptar la alimentación a ti."
        )
    else:
        text = "Sin restricciones: puedes usar las pautas generales."
    return SafetyFlags(bool(reasons), not reasons, not reasons, reasons, text)
