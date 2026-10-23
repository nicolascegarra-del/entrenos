"use client";

import { usePeriod } from "@/components/progress/period";
import {
  AcwrSection,
  FitnessSection,
  IntensitySection,
  OverallPanel,
  Section,
  VolumeSection,
  type Sections,
} from "@/components/progress/sections";
import { useInsights } from "@/hooks/use-api";

/** Progreso → Forma: estado general, forma y frescura, carga, volumen, intensidad y constancia. */
export default function Page() {
  const { days } = usePeriod();
  const { data: insights } = useInsights(days);
  const s: Sections = insights?.sections ?? {};
  return (
    <div className="grid grid-cols-1 gap-4 md:gap-6 lg:grid-cols-2">
      <div className="lg:col-span-2">
        <OverallPanel data={insights} />
      </div>
      <FitnessSection days={days} insight={s.fitness} />
      <AcwrSection data={insights} insight={s.acwr} />
      <VolumeSection days={days} insight={s.volume} />
      <IntensitySection data={insights} insight={s.intensity} />
      <Section
        title="Constancia"
        description="Regularidad de las últimas 4 semanas."
        insight={s.consistency}
        className="lg:col-span-2"
      />
    </div>
  );
}
