/**
 * Glosario de la app: cada métrica con su nombre llano, la sigla técnica (si la
 * tiene), qué significa y cómo leer su valor. Lo usan los iconos ⓘ y /glosario.
 */
export interface GlossaryEntry {
  /** Nombre en lenguaje llano, el que se muestra en la interfaz. */
  name: string;
  /** Sigla o nombre técnico, como referencia secundaria. */
  abbr?: string;
  /** Qué es, en 1–2 frases. */
  what: string;
  /** Cómo interpretar el valor. */
  read: string;
}

export const GLOSSARY = {
  load: {
    name: "Carga",
    abbr: "hrTSS",
    what: "Puntos que resumen lo duro que fue un entreno según su duración y tu frecuencia cardiaca. Una hora a ritmo de umbral son unos 100 puntos.",
    read: "Más carga = más estímulo, pero también más cansancio. Compárala con tus semanas anteriores, no con la de otras personas.",
  },
  ctl: {
    name: "Forma física",
    abbr: "CTL",
    what: "Tu carga media de las últimas ~6 semanas: refleja cuánto has entrenado de forma sostenida.",
    read: "Si sube poco a poco (hasta 5–8 puntos por semana), estás ganando forma. Si baja, estás entrenando menos de lo habitual.",
  },
  atl: {
    name: "Fatiga",
    abbr: "ATL",
    what: "Tu carga media de los últimos ~7 días: el cansancio reciente.",
    read: "Sube rápido tras días duros y baja rápido al descansar.",
  },
  tsb: {
    name: "Frescura",
    abbr: "TSB",
    what: "Forma física menos fatiga: lo descansado que llegas hoy.",
    read: "Por encima de +5, fresco. Entre −10 y +5, equilibrado (normal entrenando). Por debajo de −10, cargado; por debajo de −30, sobrecarga. Para una carrera, ideal entre +5 y +25.",
  },
  acwr: {
    name: "Carga reciente frente a la habitual",
    abbr: "ACWR",
    what: "Compara la carga de los últimos 7 días con la de las últimas 4 semanas.",
    read: "Entre 0,8 y 1,3 es la zona habitual. Por encima de 1,5 es un salto brusco, asociado a más riesgo de lesión. Por debajo de 0,8 estás entrenando menos de lo normal.",
  },
  vo2max: {
    name: "VO2max",
    abbr: "ml/kg/min",
    what: "Estimación de Garmin del oxígeno máximo que puede usar tu cuerpo por kilo y minuto: tu capacidad aeróbica.",
    read: "Más alto es mejor. Cambia despacio (semanas); fíjate en la tendencia, no en un día suelto.",
  },
  resting_hr: {
    name: "FC en reposo",
    abbr: "ppm",
    what: "Tus pulsaciones por minuto en reposo, medidas por el reloj mientras duermes.",
    read: "Bajar con los meses suele indicar mejor forma. Una subida de 5 ppm o más sobre lo habitual puede indicar cansancio, estrés o que estás incubando algo.",
  },
  vdot: {
    name: "Nivel de carrera",
    abbr: "VDOT",
    what: "Número del método Daniels calculado con tu mejor marca reciente (o tu VO2max). Resume tu nivel actual en carrera.",
    read: "Más alto es mejor. Sirve para calcular tus ritmos de entrenamiento y estimar tiempos en otras distancias.",
  },
  efficiency: {
    name: "Eficiencia aeróbica",
    what: "Metros por minuto que recorres por cada pulsación en carrera.",
    read: "Si sube con el tiempo, corres más rápido con el mismo pulso: mejora aeróbica.",
  },
  decoupling: {
    name: "Desacople",
    abbr: "Pa:FC",
    what: "Cuánto sube tu pulso (o baja tu ritmo) entre la primera y la segunda mitad de un rodaje constante.",
    read: "Por debajo del 5 % indica buena base aeróbica para esa duración. Por encima, esa distancia aún te cuesta.",
  },
  intensity: {
    name: "Distribución de intensidad",
    what: "Minutos por semana en zonas de pulso: suave (Z1–Z2), moderada (Z3) e intensa (Z4–Z5).",
    read: "Los corredores de fondo suelen hacer ~80 % suave y ~20 % moderado o intenso. Mucho tiempo en zona moderada cansa sin mejorar tanto.",
  },
  pace_curve: {
    name: "Curva de mejores ritmos",
    what: "Tu mejor ritmo sostenido durante 1, 5, 10, 20, 30 y 60 minutos, sacado de todas tus carreras. Incluye la velocidad crítica: el ritmo más rápido que se puede mantener en estado estable (unos 30–40 min).",
    read: "Si la línea del periodo actual queda por encima de la anterior, has mejorado en esa duración. Mejorar en 1–5 min indica velocidad; en 20–60 min, resistencia aeróbica.",
  },
  zones: {
    name: "Zonas de entrenamiento",
    abbr: "Friel",
    what: "Rangos de pulso y de ritmo calculados a partir de tu umbral (FC umbral y ritmo umbral). Se recalculan solos cuando tu umbral cambia.",
    read: "Z1–Z2 para rodajes suaves (la mayor parte del entrenamiento), Z3 tempo, Z4 umbral y Z5 series cortas e intensas.",
  },
  predictions: {
    name: "Tiempos estimados",
    abbr: "Riegel",
    what: "Tiempos previstos en otras distancias a partir de tus mejores marcas (fórmula de Riegel).",
    read: "Son orientativos: suponen que entrenas la distancia. En distancias más largas que tus tiradas, el tiempo real suele ser peor.",
  },
  age_grade: {
    name: "Ajuste por edad",
    what: "Compara tu marca con el récord mundial para tu edad y sexo (tablas WMA), en porcentaje.",
    read: "60 % nivel local, 70 % regional, 80 % nacional, 90 % élite mundial.",
  },
  compliance: {
    name: "Cumplimiento del plan",
    what: "Cuánto se parece lo que hiciste a la sesión que planificaste, vuelta a vuelta.",
    read: "90 % o más, cumplida (verde). Entre 70 y 90 %, cerca (ámbar). Por debajo de 70 %, la sesión fue bastante distinta de lo previsto (rojo).",
  },
  rpe: {
    name: "Esfuerzo percibido",
    abbr: "RPE",
    what: "Lo duro que te pareció el entreno, de 1 (muy fácil) a 10 (máximo).",
    read: "Sirve para calcular la carga cuando no hay pulso y para detectar días en que todo cuesta más de lo normal.",
  },
  readiness: {
    name: "Recuperación (readiness)",
    abbr: "Oura",
    what: "Puntuación de 0 a 100 del anillo Oura que resume lo recuperado que estás: sueño, FC en reposo, HRV, temperatura y actividad de los días anteriores.",
    read: "85 o más, óptima; de 70 a 84, buena; por debajo de 70, conviene ir con calma. Mira qué contribuidor la baja para saber por qué.",
  },
  skin_temperature: {
    name: "Temperatura de la piel",
    what: "Diferencia entre tu temperatura de la piel durante la noche y tu referencia habitual, en grados. No es tu temperatura corporal.",
    read: "Cerca de 0 es lo normal. Subidas de +0,5 °C o más, sobre todo varios días seguidos, pueden indicar que estás incubando algo, el ciclo menstrual, alcohol o calor.",
  },
  breathing_disturbance: {
    name: "Índice de alteraciones respiratorias",
    abbr: "BDI",
    what: "Cuántas veces por hora de sueño baja de forma notable tu oxígeno en sangre (SpO2), según el anillo.",
    read: "Por debajo de 5, normal; de 5 a 15, moderado; por encima de 15, alto. No es un diagnóstico: si sale alto a menudo, coméntalo con tu médico.",
  },
  resilience: {
    name: "Resiliencia",
    abbr: "Oura",
    what: "Cómo aguantas el estrés a lo largo de varias semanas, según cuánto te recuperas durmiendo y de día frente al estrés que acumulas.",
    read: "De menos a más: limitada, suficiente, sólida, fuerte y excepcional. Mejora con buen sueño, días tranquilos y carga bien repartida.",
  },
  vascular_age: {
    name: "Edad vascular",
    abbr: "Cardiovascular age",
    what: "Edad que corresponde a la rigidez de tus arterias, estimada por el anillo a partir de la velocidad de la onda de pulso.",
    read: "Si es menor que tu edad real, tus arterias están más elásticas que la media. Cambia despacio: fíjate en la tendencia de meses.",
  },
  pulse_wave: {
    name: "Velocidad de la onda de pulso",
    abbr: "PWV",
    what: "Lo rápido que viaja cada latido por tus arterias, en metros por segundo. Cuanto más rígidas, más rápido va.",
    read: "Más bajo es mejor. El ejercicio aeróbico regular tiende a bajarla con los meses.",
  },
  hypnogram: {
    name: "Hipnograma",
    what: "Gráfico de tu noche que muestra, minuto a minuto, en qué fase estabas: despierto, REM, sueño ligero o profundo.",
    read: "Lo normal es pasar por 4–6 ciclos: más sueño profundo al principio de la noche y más REM al final. Despertares cortos son normales.",
  },
} satisfies Record<string, GlossaryEntry>;

export type GlossaryKey = keyof typeof GLOSSARY;
