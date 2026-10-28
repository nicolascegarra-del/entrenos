"use client";

import { CalendarDays, ChevronRight, Moon } from "lucide-react";
import Link from "next/link";

import { usePeriod } from "@/components/progress/period";
import {
  ContributorSection,
  InjurySection,
  MetricSection,
  MultiMetricSection,
  type Sections,
} from "@/components/progress/sections";
import { useInsights } from "@/hooks/use-api";
import { resilienceLevelName } from "@/lib/oura";
import { toIsoDay } from "@/lib/plan";

const toH = (v: number) => v / 3600;
const toMin = (v: number) => v / 60;

/** Accesos a la última noche y al día de hoy (hipnograma, curvas, FC por origen…). */
function NightDayLinks() {
  const today = toIsoDay(new Date());
  const links = [
    {
      href: `/progresion/salud/noche/${today}`,
      icon: Moon,
      title: "Tu última noche",
      text: "Hipnograma, FC y HRV de la noche, puntuaciones y horario recomendado.",
    },
    {
      href: `/progresion/salud/dia/${today}`,
      icon: CalendarDays,
      title: "Tu día de hoy",
      text: "FC continua, actividad cada 5 minutos, estrés y sesiones.",
    },
  ];
  return (
    <ul className="grid gap-2 sm:grid-cols-2 lg:col-span-2">
      {links.map(({ href, icon: Icon, title, text }) => (
        <li key={href}>
          <Link
            href={href}
            className="flex min-h-14 items-center gap-3 rounded-lg border bg-card p-3 shadow-sm hover:bg-muted/60"
          >
            <Icon className="size-5 shrink-0 text-klyp-accent" aria-hidden />
            <span className="min-w-0 flex-1">
              <span className="block font-medium">{title}</span>
              <span className="block text-xs text-muted-foreground">
                {text}
              </span>
            </span>
            <ChevronRight
              className="size-4 shrink-0 text-muted-foreground"
              aria-hidden
            />
          </Link>
        </li>
      ))}
    </ul>
  );
}

/**
 * Progreso → Salud: prevención de lesiones, FC en reposo, VO2max y sueño, más lo que traiga el
 * anillo Oura (recuperación, temperatura, SpO2, estrés, fases del sueño…). Las métricas que no
 * tienen datos no se enseñan.
 */
export default function Page() {
  const { days } = usePeriod();
  const { data: insights } = useInsights(days);
  const s: Sections = insights?.sections ?? {};
  const sleepDays = Math.min(days, 120);
  return (
    <div className="grid grid-cols-1 gap-4 md:gap-6 lg:grid-cols-2">
      <NightDayLinks />
      <InjurySection />
      <MetricSection
        title="FC en reposo"
        term="resting_hr"
        metric="resting_hr"
        days={days}
        unit="ppm"
        color="var(--chart-2)"
        description="Comparada con tu propia referencia de los últimos 30 días."
        insight={s.resting_hr}
      />
      <MetricSection
        title="VO2max"
        term="vo2max"
        metric="vo2max"
        days={days}
        unit="ml/kg/min"
        color="var(--chart-4)"
        description="Estimación de Garmin tras cada carrera."
        insight={s.vo2max}
      />
      <MetricSection
        title="Sueño"
        metric="sleep_seconds"
        days={sleepDays}
        unit="h"
        decimals={1}
        color="var(--chart-1)"
        transform={toH}
        description="Horas por noche."
        insight={s.recovery}
      />

      {/* Recuperación (Oura) */}
      <MetricSection
        hideEmpty
        title="Recuperación"
        term="readiness"
        metric="readiness_score"
        days={days}
        unit="/100"
        color="var(--chart-1)"
        yDomain={[0, 100]}
        description="Puntuación diaria de Oura (0–100)."
      />
      <ContributorSection
        title="Qué mueve tu recuperación"
        description="Cada contribuidor de 0 a 100: elige cuál ver."
        days={days}
        scoreMetric="readiness_score"
        prefix="oura_readiness_"
        kind="readiness"
        color="var(--chart-1)"
      />
      <MetricSection
        hideEmpty
        title="Puntuación de sueño"
        metric="sleep_score"
        days={sleepDays}
        unit="/100"
        color="var(--chart-4)"
        yDomain={[0, 100]}
      />
      <ContributorSection
        title="Qué mueve tu sueño"
        description="Cada contribuidor de 0 a 100: elige cuál ver."
        days={sleepDays}
        scoreMetric="sleep_score"
        prefix="oura_sleep_"
        kind="sleep"
        color="var(--chart-4)"
      />
      <MetricSection
        hideEmpty
        title="Variabilidad de la FC (HRV)"
        metric="hrv_last_night"
        days={days}
        unit="ms"
        color="var(--chart-3)"
        description="HRV media de cada noche."
      />
      <MultiMetricSection
        title="Temperatura de la piel"
        term="skin_temperature"
        description="Diferencia con tu referencia, cada noche y su tendencia."
        days={days}
        unit="°C"
        decimals={1}
        metrics={[
          {
            key: "temperature_deviation",
            label: "Desviación",
            color: "var(--chart-2)",
          },
          {
            key: "temperature_trend_deviation",
            label: "Tendencia",
            color: "var(--chart-5)",
          },
        ]}
      />

      {/* Sueño en detalle */}
      <MultiMetricSection
        title="Fases del sueño"
        description="Horas por noche en cada fase."
        days={sleepDays}
        unit="h"
        decimals={1}
        transform={toH}
        kind="bar"
        className="lg:col-span-2"
        metrics={[
          {
            key: "sleep_deep_s",
            label: "Profundo",
            color: "var(--intensity-high)",
          },
          { key: "sleep_rem_s", label: "REM", color: "var(--intensity-mid)" },
          {
            key: "sleep_light_s",
            label: "Ligero",
            color: "var(--intensity-low)",
          },
          { key: "sleep_awake_s", label: "Despierto", color: "var(--chart-2)" },
        ]}
      />
      <MetricSection
        hideEmpty
        title="Eficiencia del sueño"
        metric="sleep_efficiency"
        days={sleepDays}
        unit="%"
        color="var(--chart-1)"
        description="Parte del tiempo en la cama que pasas dormido."
      />
      <MetricSection
        hideEmpty
        title="Latencia"
        metric="sleep_latency_s"
        days={sleepDays}
        unit="min"
        transform={toMin}
        color="var(--chart-4)"
        description="Minutos que tardas en dormirte."
      />
      <MetricSection
        hideEmpty
        title="Tiempo en la cama"
        metric="time_in_bed_s"
        days={sleepDays}
        unit="h"
        decimals={1}
        transform={toH}
        color="var(--chart-5)"
      />
      <MetricSection
        hideEmpty
        title="Inquietud"
        metric="restless_periods"
        days={sleepDays}
        unit="periodos"
        color="var(--chart-5)"
        description="Periodos de movimiento durante la noche."
      />
      <MetricSection
        hideEmpty
        title="FC media durmiendo"
        metric="avg_hr_sleep"
        days={sleepDays}
        unit="ppm"
        color="var(--chart-2)"
      />
      <MetricSection
        hideEmpty
        title="Respiración"
        metric="breath_rate"
        days={sleepDays}
        unit="rpm"
        decimals={1}
        color="var(--chart-3)"
        description="Respiraciones por minuto durante el sueño."
      />
      <MetricSection
        hideEmpty
        title="Siestas"
        metric="naps_s"
        days={sleepDays}
        unit="min"
        transform={toMin}
        color="var(--chart-4)"
        description="Minutos de siesta por día."
      />

      {/* Oxígeno */}
      <MetricSection
        hideEmpty
        title="SpO2"
        metric="spo2_avg"
        days={days}
        unit="%"
        decimals={1}
        color="var(--chart-1)"
        description="Saturación media de oxígeno en sangre durante la noche."
      />
      <MetricSection
        hideEmpty
        title="Alteraciones respiratorias"
        term="breathing_disturbance"
        metric="breathing_disturbance_index"
        days={days}
        unit="/h"
        color="var(--chart-2)"
      />

      {/* Estrés y resiliencia */}
      <MultiMetricSection
        title="Estrés y recuperación de día"
        description="Minutos al día con estrés alto y con recuperación alta."
        days={days}
        unit="min"
        transform={toMin}
        metrics={[
          {
            key: "stress_high_s",
            label: "Estrés alto",
            color: "var(--chart-2)",
          },
          {
            key: "recovery_high_s",
            label: "Recuperación alta",
            color: "var(--chart-3)",
          },
        ]}
      />
      <MetricSection
        hideEmpty
        title="Estrés medio"
        metric="stress_avg"
        days={days}
        unit=""
        color="var(--chart-2)"
      />
      <MetricSection
        hideEmpty
        title="Resiliencia"
        term="resilience"
        metric="resilience_level"
        days={days}
        unit=""
        color="var(--chart-3)"
        yDomain={[1, 5]}
        format={resilienceLevelName}
      />
      <ContributorSection
        title="Qué mueve tu resiliencia"
        days={days}
        scoreMetric="resilience_level"
        prefix="oura_resilience_"
        kind="resilience"
        color="var(--chart-3)"
      />

      {/* Corazón y vasos */}
      <MetricSection
        hideEmpty
        title="VO2max (Oura)"
        term="vo2max"
        metric="vo2max_oura"
        days={days}
        unit="ml/kg/min"
        color="var(--chart-4)"
        description="Estimación del anillo con su test de caminar."
      />
      <MetricSection
        hideEmpty
        title="Edad vascular"
        term="vascular_age"
        metric="cardio_age"
        days={days}
        unit="años"
        color="var(--chart-4)"
      />
      <MetricSection
        hideEmpty
        title="Onda de pulso"
        term="pulse_wave"
        metric="pulse_wave_velocity"
        days={days}
        unit="m/s"
        decimals={1}
        color="var(--chart-5)"
      />

      {/* Actividad diaria */}
      <MetricSection
        hideEmpty
        title="Puntuación de actividad"
        metric="activity_score"
        days={days}
        unit="/100"
        color="var(--chart-2)"
        yDomain={[0, 100]}
      />
      <ContributorSection
        title="Qué mueve tu actividad"
        days={days}
        scoreMetric="activity_score"
        prefix="oura_activity_"
        kind="activity"
        color="var(--chart-2)"
      />
      <MetricSection
        hideEmpty
        title="Pasos"
        metric="steps_daily"
        days={days}
        unit="pasos"
        color="var(--chart-1)"
      />
      <MultiMetricSection
        title="Calorías"
        description="Activas y totales por día."
        days={days}
        unit="kcal"
        metrics={[
          {
            key: "active_calories",
            label: "Activas",
            color: "var(--chart-2)",
          },
          { key: "total_calories", label: "Totales", color: "var(--chart-5)" },
        ]}
      />
    </div>
  );
}
