import { TrendingUp } from "lucide-react";

import { ComingSoon } from "@/components/coming-soon";

export default function ProgresionPage() {
  return (
    <ComingSoon
      title="Progresión"
      icon={TrendingUp}
      phase="Fase 5"
      description="Volumen semanal, VO2max, FC en reposo, eficiencia aeróbica y mejores marcas a lo largo del tiempo."
    />
  );
}
