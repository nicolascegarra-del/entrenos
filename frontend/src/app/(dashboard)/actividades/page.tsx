import { Footprints } from "lucide-react";

import { ComingSoon } from "@/components/coming-soon";

export default function ActividadesPage() {
  return (
    <ComingSoon
      title="Actividades"
      icon={Footprints}
      phase="Fase 3"
      description="Listado y detalle de tus actividades sincronizadas desde Garmin, con mapa, gráficas y vueltas."
    />
  );
}
