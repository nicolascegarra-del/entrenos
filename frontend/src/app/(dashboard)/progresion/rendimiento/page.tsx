"use client";

import { usePeriod } from "@/components/progress/period";
import {
  EfficiencySection,
  PaceCurveSection,
  RecordsSection,
  ZonesSection,
  type Sections,
} from "@/components/progress/sections";
import { TestsCard } from "@/components/tests/tests-card";
import { useInsights } from "@/hooks/use-api";

/** Progreso → Rendimiento: tests, curva de ritmos, eficiencia, zonas y marcas. */
export default function Page() {
  const { days } = usePeriod();
  const { data: insights } = useInsights(days);
  const s: Sections = insights?.sections ?? {};
  return (
    <div className="grid grid-cols-1 gap-4 md:gap-6 lg:grid-cols-2">
      <TestsCard />
      <PaceCurveSection days={days} />
      <EfficiencySection days={days} insight={s.efficiency} data={insights} />
      <ZonesSection />
      <RecordsSection insight={s.records} data={insights} />
    </div>
  );
}
