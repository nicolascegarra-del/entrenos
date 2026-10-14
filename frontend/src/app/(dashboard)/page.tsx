import { LayoutDashboard } from "lucide-react";

import { ComingSoon } from "@/components/coming-soon";

export default function ResumenPage() {
  return (
    <ComingSoon
      title="Resumen"
      icon={LayoutDashboard}
      phase="Fase 5"
      description="Aquí verás tu semana de un vistazo: carga, forma (CTL/ATL/TSB), cumplimiento del plan y últimas actividades."
    />
  );
}
