"use client";

import { usePeriod } from "@/components/progress/period";
import {
  InjurySection,
  MetricSection,
  type Sections,
} from "@/components/progress/sections";
import { useInsights } from "@/hooks/use-api";

/** Progreso → Salud: prevención de lesiones, FC en reposo, VO2max y sueño. */
export default function Page() {
  const { days } = usePeriod();
  const { data: insights } = useInsights(days);
  const s: Sections = insights?.sections ?? {};
  return (
    <div className="grid grid-cols-1 gap-4 md:gap-6 lg:grid-cols-2">
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
        days={Math.min(days, 120)}
        unit="h"
        decimals={1}
        color="var(--chart-1)"
        transform={(v) => v / 3600}
        description="Horas por noche (Garmin)."
        insight={s.recovery}
      />
    </div>
  );
}
