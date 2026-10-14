import { CalendarDays } from "lucide-react";

import { ComingSoon } from "@/components/coming-soon";

export default function PlanPage() {
  return (
    <ComingSoon
      title="Plan"
      icon={CalendarDays}
      phase="Fase 4"
      description="Planifica sesiones por bloques y compáralas con lo que registró tu reloj: cumplimiento por intervalo."
    />
  );
}
